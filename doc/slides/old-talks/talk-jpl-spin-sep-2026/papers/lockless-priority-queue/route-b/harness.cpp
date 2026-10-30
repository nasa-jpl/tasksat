// ======================================================================
// Route B: standalone harness reproducing the m_available underflow in
// Os::Generic::LocklessPriorityQueue (nasa/fprime PR #5076).
//
// The send()/receive() logic below is transcribed FAITHFULLY from
// ../src/LocklessPriorityQueue.cpp (lines ~197-354), with the F' dependencies
// stubbed:  FW_ASSERT -> assert,  MemAllocator -> new[],  FwQueuePriorityType
// -> int32_t,  LocklessStateTagType -> uint64_t.  See ../report.md section 1
// for why this is NOT a substitute for building inside F' (Route A) -- most
// importantly it says nothing about whether the atomics are lock-free on the
// real flight target.
//
// THE ONLY ADDED INSTRUMENTATION is hookAfterPublish(): a delay inserted at
// the exact point between the READY store and the m_available increment
// (src line 240 -> 244).  A producer preempted there is an ordinary scheduling
// event; the delay does not create an impossible interleaving, it just widens
// a window that already exists so the natural thread race lands in it.
//
// Build & run: see run.sh in this folder.
// ======================================================================
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <thread>
#include <vector>

// ---- stubbed F' types ----
using U8 = uint8_t;
using U32 = uint32_t;
using FwSizeType = size_t;
using FwQueuePriorityType = int32_t;
using LocklessStateTagType = uint64_t;

// ---- global config / instrumentation (test-only, does not alter algorithm) ----
static bool     g_fixed   = false;   // --fixed: move m_available increment BEFORE publish
static int      g_delayUs = 50;      // delay injected at the publish->increment seam
static std::atomic<bool>     g_underflow{false};
static std::atomic<uint32_t> g_badValue{0};
static std::atomic<bool>     g_stop{false};
static std::atomic<uint64_t> g_maxAvailObserved{0};

// The seam.  Models a producer being descheduled between publishing READY and
// bumping m_available.  Enabled only in the buggy ordering; the point is that
// this delay could occur naturally from an interrupt or the scheduler.
static inline void hookAfterPublish() {
    if (g_delayUs > 0) {
        std::this_thread::sleep_for(std::chrono::microseconds(g_delayUs));
    }
}

// ---- slot state machine (verbatim constants from the PR) ----
enum : LocklessStateTagType { FREE = 0, WRITING = 1, READY = 2, READING = 3 };
static const LocklessStateTagType STATE_BITS = 2;
static const LocklessStateTagType STATE_MASK = 0x3;

static inline LocklessStateTagType stateOf(LocklessStateTagType p) { return p & STATE_MASK; }
static inline LocklessStateTagType tagOf(LocklessStateTagType p)   { return p >> STATE_BITS; }
static inline LocklessStateTagType packStateTag(LocklessStateTagType s, LocklessStateTagType t) {
    return (t << STATE_BITS) | (s & STATE_MASK);
}

struct Slot {
    std::atomic<LocklessStateTagType> m_stateTag;
    std::atomic<U32>                  m_sequence;
    FwSizeType                        m_size;      // non-atomic: owner-only, as in the PR
    std::atomic<FwQueuePriorityType>  m_priority;
    Slot() : m_stateTag(packStateTag(FREE, 0)), m_sequence(0), m_size(0), m_priority(0) {}
};

class Queue {
  public:
    void create(FwSizeType depth, FwSizeType messageSize) {
        m_depth = depth;
        m_messageSize = messageSize;
        m_slots = new Slot[depth];
        m_data  = new U8[depth * messageSize];
        m_sequence.store(0);
        m_count.store(0);
        m_available.store(0);
        m_highMark.store(0);
    }
    ~Queue() { delete[] m_slots; delete[] m_data; }

    // Faithful transcription of send() with the publish/increment seam.
    bool send(const U8* buffer, FwSizeType size, FwQueuePriorityType priority) {
        assert(m_slots != nullptr && m_data != nullptr && buffer != nullptr);
        if (size > m_messageSize) return false;
        const FwSizeType depth = m_depth;
        for (;;) {                                  // blocking-style: retry until a slot frees
            if (g_stop.load(std::memory_order_relaxed)) return false;
            for (FwSizeType i = 0; i < depth; i++) {
                Slot& slot = m_slots[i];
                LocklessStateTagType packed = slot.m_stateTag.load(std::memory_order_acquire);
                if (stateOf(packed) != FREE) continue;
                const LocklessStateTagType desired = packStateTag(WRITING, tagOf(packed) + 1);
                if (slot.m_stateTag.compare_exchange_strong(packed, desired,
                        std::memory_order_acq_rel, std::memory_order_relaxed)) {
                    if (size > 0) {
                        std::memcpy(m_data + i * m_messageSize, buffer, size);
                    }
                    slot.m_size = size;
                    slot.m_priority.store(priority, std::memory_order_relaxed);
                    slot.m_sequence.store(m_sequence.fetch_add(1, std::memory_order_relaxed),
                                          std::memory_order_relaxed);
                    const U32 nextCount = m_count.fetch_add(1, std::memory_order_acq_rel) + 1;

                    if (g_fixed) {
                        // FIX (report.md section 6): increment BEFORE publishing READY.
                        m_available.fetch_add(1, std::memory_order_acq_rel);
                        slot.m_stateTag.store(packStateTag(READY, tagOf(desired) + 1),
                                              std::memory_order_release);
                    } else {
                        // PR AS WRITTEN: publish READY, [seam], then increment.
                        slot.m_stateTag.store(packStateTag(READY, tagOf(desired) + 1),
                                              std::memory_order_release);
                        hookAfterPublish();                                   // <-- the natural window
                        m_available.fetch_add(1, std::memory_order_acq_rel);
                    }

                    U32 prevMark = m_highMark.load(std::memory_order_relaxed);
                    for (FwSizeType mp = 0; (mp < depth) && (nextCount > prevMark); mp++) {
                        if (m_highMark.compare_exchange_strong(prevMark, nextCount,
                                std::memory_order_relaxed, std::memory_order_relaxed)) break;
                    }
                    return true;
                }
            }
        }
    }

    // Faithful transcription of receive() (non-blocking scan; the caller loops).
    bool receive(U8* destination, FwSizeType capacity, FwSizeType& actualSize,
                 FwQueuePriorityType& priority) {
        assert(m_slots != nullptr && m_data != nullptr && destination != nullptr);
        const FwSizeType depth = m_depth;

        // Fast-path gate: a PEEK at m_available, its own step (src line 283).
        if (m_available.load(std::memory_order_acquire) == 0) return false;

        FwSizeType bestIndex = depth;
        FwQueuePriorityType bestPriority = FwQueuePriorityType();
        U32 bestSequence = 0;
        LocklessStateTagType bestPacked = 0;

        for (FwSizeType i = 0; i < depth; i++) {
            Slot& slot = m_slots[i];
            LocklessStateTagType packed = slot.m_stateTag.load(std::memory_order_acquire);
            if (stateOf(packed) != READY) continue;
            const FwQueuePriorityType cp = slot.m_priority.load(std::memory_order_relaxed);
            const U32 cs = slot.m_sequence.load(std::memory_order_relaxed);
            const LocklessStateTagType recheck = slot.m_stateTag.load(std::memory_order_acquire);
            if (packed != recheck) continue;
            if (bestIndex == depth || isCandidatePreferred(cp, cs, bestPriority, bestSequence)) {
                bestIndex = i; bestPriority = cp; bestSequence = cs; bestPacked = packed;
            }
        }
        if (bestIndex == depth) return false;

        const LocklessStateTagType desired = packStateTag(READING, tagOf(bestPacked) + 1);
        if (m_slots[bestIndex].m_stateTag.compare_exchange_strong(bestPacked, desired,
                std::memory_order_acq_rel, std::memory_order_relaxed)) {
            // The decrement.  fetch_sub returns the PREVIOUS value; prev==0 IS the underflow.
            const uint32_t prevAvail = m_available.fetch_sub(1, std::memory_order_acq_rel);
            if (prevAvail == 0) {
                g_underflow.store(true, std::memory_order_relaxed);
                g_badValue.store(m_available.load(std::memory_order_acquire), std::memory_order_relaxed);
                g_stop.store(true, std::memory_order_relaxed);
            }
            Slot& slot = m_slots[bestIndex];
            const FwSizeType storedSize = slot.m_size;
            assert(storedSize <= capacity);
            if (storedSize > 0) {
                std::memcpy(destination, m_data + bestIndex * m_messageSize, storedSize);
            }
            actualSize = storedSize;
            priority = slot.m_priority.load(std::memory_order_relaxed);
            m_count.fetch_sub(1, std::memory_order_acq_rel);
            slot.m_stateTag.store(packStateTag(FREE, tagOf(desired) + 1), std::memory_order_release);
            return true;
        }
        return false;  // lost the CAS; caller rescans
    }

    uint32_t getMessagesAvailable() const { return m_available.load(std::memory_order_acquire); }
    FwSizeType depth() const { return m_depth; }

  private:
    static bool isCandidatePreferred(FwQueuePriorityType cp, U32 cs,
                                     FwQueuePriorityType bp, U32 bs) {
        if (cp > bp) return true;
        if (cp == bp) {
            const U32 diff = cs - bs;
            const U32 topBit = static_cast<U32>(1) << (std::numeric_limits<U32>::digits - 1);
            return (diff & topBit) != 0;
        }
        return false;
    }
    Slot*       m_slots = nullptr;
    U8*         m_data  = nullptr;
    FwSizeType  m_depth = 0;
    FwSizeType  m_messageSize = 0;
    std::atomic<U32> m_sequence{0};
    std::atomic<U32> m_count{0};
    std::atomic<U32> m_available{0};
    std::atomic<U32> m_highMark{0};
};

// ---------------------------------------------------------------------------
int main(int argc, char** argv) {
    FwSizeType depth = 16;
    size_t total = 2000000;      // upper bound; buggy run exits early on first underflow
    int producers = 2, consumers = 4;
    for (int a = 1; a < argc; a++) {
        std::string s = argv[a];
        if (s == "--fixed") g_fixed = true;
        else if (s == "--delay-us" && a + 1 < argc) g_delayUs = atoi(argv[++a]);
        else if (s == "--total"    && a + 1 < argc) total = strtoull(argv[++a], nullptr, 10);
        else if (s == "--depth"    && a + 1 < argc) depth = strtoull(argv[++a], nullptr, 10);
    }

    Queue q;
    q.create(depth, sizeof(uint32_t));

    std::vector<std::atomic<uint32_t>> delivered(total);   // exactly-once tracking
    for (auto& d : delivered) d.store(0);
    std::atomic<size_t> nextId{0};
    std::atomic<size_t> received{0};

    // Monitor thread: samples getMessagesAvailable() like telemetry would.
    std::thread monitor([&] {
        while (!g_stop.load(std::memory_order_relaxed) &&
               received.load(std::memory_order_relaxed) < total) {
            uint64_t v = q.getMessagesAvailable();
            uint64_t prev = g_maxAvailObserved.load(std::memory_order_relaxed);
            while (v > prev && !g_maxAvailObserved.compare_exchange_weak(prev, v)) {}
        }
    });

    auto producerFn = [&] {
        for (;;) {
            if (g_stop.load(std::memory_order_relaxed)) return;
            size_t id = nextId.fetch_add(1, std::memory_order_relaxed);
            if (id >= total) return;
            uint32_t payload = static_cast<uint32_t>(id);
            // vary priority a little so selection logic is exercised
            q.send(reinterpret_cast<U8*>(&payload), sizeof(payload),
                   static_cast<FwQueuePriorityType>(id % 4));
        }
    };
    auto consumerFn = [&] {
        uint32_t buf; FwSizeType sz; FwQueuePriorityType pr;
        while (received.load(std::memory_order_relaxed) < total) {
            if (g_stop.load(std::memory_order_relaxed)) {
                // in buggy mode we stop the world on first underflow
                if (!g_fixed) return;
            }
            if (q.receive(reinterpret_cast<U8*>(&buf), sizeof(buf), sz, pr)) {
                assert(sz == sizeof(uint32_t));
                uint32_t prevCount = delivered[buf].fetch_add(1, std::memory_order_relaxed);
                assert(prevCount == 0 && "exactly-once violated: duplicate delivery");
                received.fetch_add(1, std::memory_order_relaxed);
            }
        }
    };

    std::vector<std::thread> ts;
    for (int i = 0; i < producers; i++) ts.emplace_back(producerFn);
    for (int i = 0; i < consumers; i++) ts.emplace_back(consumerFn);
    for (auto& t : ts) t.join();
    g_stop.store(true);
    monitor.join();

    printf("mode          : %s\n", g_fixed ? "FIXED (increment before publish)"
                                           : "PR AS WRITTEN (increment after publish)");
    printf("depth         : %zu\n", depth);
    printf("seam delay    : %d us\n", g_delayUs);
    printf("messages recvd: %zu\n", received.load());
    printf("max available observed by 'telemetry' : %llu\n",
           (unsigned long long)g_maxAvailObserved.load());
    if (g_underflow.load()) {
        printf(">>> UNDERFLOW DETECTED: m_available wrapped; getMessagesAvailable() would read %u (0x%08X)\n",
               g_badValue.load(), g_badValue.load());
        printf(">>> (delivery itself stayed correct up to the stop point: no duplicate fired the assert)\n");
        return 2;
    } else {
        printf("no underflow observed. ");
        if (g_fixed) {
            // In fixed mode we ran to completion; verify exactly-once and the bound.
            size_t missing = 0, dup = 0;
            for (auto& d : delivered) { uint32_t c = d.load(); if (c == 0) missing++; else if (c > 1) dup++; }
            printf("exactly-once: missing=%zu dup=%zu; max available (<= depth expected) = %llu\n",
                   missing, dup, (unsigned long long)g_maxAvailObserved.load());
            return (missing == 0 && dup == 0 && g_maxAvailObserved.load() <= depth) ? 0 : 3;
        }
        printf("(try a larger --total or --delay-us to widen the race)\n");
        return 0;
    }
}
