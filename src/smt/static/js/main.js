// TaskSAT Web Interface - Main JavaScript

// Initialize tooltips
document.addEventListener('DOMContentLoaded', function() {
    // Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Add click feedback to all buttons
    document.querySelectorAll('.btn').forEach(button => {
        button.addEventListener('click', function() {
            // Add clicked class for animation
            this.classList.add('clicked');

            // Remove class after animation completes
            setTimeout(() => {
                this.classList.remove('clicked');
            }, 200);
        });
    });

    console.log('TaskSAT Web Interface loaded');
});

// Image zoom functionality
function openImageModal(src) {
    const modalImage = document.getElementById('modalImage');
    if (modalImage) {
        modalImage.src = src;
        const modal = new bootstrap.Modal(document.getElementById('imageModal'));
        modal.show();
    }
}

// Smooth scroll
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth'
            });
        }
    });
});

// Auto-refresh: poll for new/updated verification results
let lastTasknetsState = null;

function checkForUpdates() {
    // Only poll on index page (has tasknet cards)
    if (!document.querySelector('.tasknet-card')) {
        return;
    }

    fetch('/api/tasknets')
        .then(response => response.json())
        .then(data => {
            const currentState = JSON.stringify(data.sort((a, b) => a.name.localeCompare(b.name)));

            // If state changed, reload page
            if (lastTasknetsState && lastTasknetsState !== currentState) {
                console.log('New verification results detected, reloading...');
                window.location.reload();
            }

            lastTasknetsState = currentState;
        })
        .catch(error => {
            console.error('Error checking for updates:', error);
        });
}

// Poll every 5 seconds
setInterval(checkForUpdates, 5000);
// Initial check
checkForUpdates();
