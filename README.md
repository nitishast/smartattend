Complete Separation: Each template is now in its own file.

Base Template (base.html): This provides the common structure (navbar, CSS, JavaScript) and uses {% block content %} and {% block title %} to allow other templates to inherit and customize. It also handles flashed messages.

Bootstrap: Uses Bootstrap for styling, making the UI look much better.

Modals: Uses Bootstrap modals for forms like "Add Class", making the UI cleaner.

Error Pages: Includes basic 404 and 500 error pages.

Chart.js: The admin dashboard uses Chart.js for a simple attendance chart.

** Placeholders and Comments**: Added the plcaeholders and comments wherever required.
-
 First-Time Setup and Usage:

Admin User: The application automatically creates an admin user on the first run if no users exist. The credentials are:

Username: admin

Password: admin

Change this password immediately! Go to the /auth/profile page after logging in as admin to change the password.

Adding Students:

Login as Admin.

Go to students' page and add the student. While adding the student, add the required images of the student.

Adding Cameras:

Login as Admin.

Go to Camera page and add the new camera.

Starting Attendance:
* Login as Teacher.
* Go to Attendance page and start a session.