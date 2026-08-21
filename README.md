# TaskSAT 

TaskSAT is a domain-specific language and tool for modeling and verifying task scheduling problems with rich temporal and resource constraints, combining a declarative specification language with SMT-based automated reasoning using Z3. It can be applied to scheduling problems in autonomous systems, such as spacecraft and rover operations.

## Documentation

Full documentation — overview, key features, getting started, tutorial, language manual, grammar, and the theory behind the SMT encoding — is published at:

**[https://nasa-jpl.github.io/tasksat/](https://nasa-jpl.github.io/tasksat/)**

The docs source lives in [`website/docs/`](website/docs/) and is built with [Docusaurus](https://docusaurus.io/). To preview locally: `cd website && npm install && npm start`.


## License, Copyright, Permissions, Disclaimer

APACHE LICENSE, VERSION 2.0: https://www.apache.org/licenses/LICENSE-2.0.txt

Copyright 2026, by the California Institute of Technology. ALL RIGHTS RESERVED. United States Government Sponsorship acknowledged. Any commercial use must be negotiated with the Office of Technology Transfer at the California Institute of Technology.
 
This software may be subject to U.S. export control laws. By accepting this software, the user agrees to comply with all applicable U.S. export laws and regulations. User has the responsibility to obtain export licenses, or other export authority as may be required before exporting such information to foreign countries or providing access to foreign persons.

-  Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer. 
- Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution. 
- Neither the name of Caltech nor its operating division, the Jet Propulsion Laboratory, nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission. 

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE. 

## Contribution

- Klaus Havelund <klaus.havelund@jpl.nasa.gov>
- Alessandro Pinto <alessandro.pinto@jpl.nasa.gov>

TaskSAT has been developed with substantial assistance from large language
models (a practice colloquially known as "vibe coding"): the authors directed
the design, review, and validation, while much of the implementation was carried
out through AI-assisted, agentic coding workflows.
