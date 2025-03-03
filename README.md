Complete Separation: Each template is now in its own file.

Base Template (base.html): This provides the common structure (navbar, CSS, JavaScript) and uses {% block content %} and {% block title %} to allow other templates to inherit and customize. It also handles flashed messages.

Bootstrap: Uses Bootstrap for styling, making the UI look much better.

Modals: Uses Bootstrap modals for forms like "Add Class", making the UI cleaner.

Error Pages: Includes basic 404 and 500 error pages.

Chart.js: The admin dashboard uses Chart.js for a simple attendance chart.

** Placeholders and Comments**: Added the plcaeholders and comments wherever required.