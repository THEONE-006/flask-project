# Flask Approval Workflow System

A Flask-based request approval system that routes requests through multiple approvers using email notifications.

## Features

- User login with OTP verification
- Multi-stage approval workflow
- Email notifications to approvers
- One-click Approve/Reject links
- Tracks current approver
- Approval history
- SQLite database with SQLAlchemy
- Flask-Migrate support

## Technologies Used

- Python 3
- Flask
- Flask-SQLAlchemy
- Flask-Migrate
- SQLite
- HTML/CSS

## Environment Variables

Create a `.env` file in the project root and add the following variables:

```env
SECRET_KEY=your_secret_key_here

MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_gmail_app_password

OTP_EXPIRY_MINUTES=10
```

You can start by copying the example file:

```bash
cp .env.example .env
```

On Windows Command Prompt:

```cmd
copy .env.example .env
```

Or simply duplicate the file and rename it to `.env`.

## Installation

```bash
git clone https://github.com/THEONE-006/flask-project.git
cd flask-project

python -m venv venv
```

Activate the virtual environment:

Windows:

```bash
venv\Scripts\activate
```

Linux/macOS:

```bash
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a `.env` file (see **Environment Variables** above), then initialize the database if required:

```bash
flask db upgrade
```

Run the application:

```bash
flask run
```

## Adding a New Request Type

Request types and approval stages are configured in `config.py`.

When adding a new approval stage that sends email, create a corresponding
environment variable in `.env`.

Example:

```python
{
    "stage": "Security Review",
    "email": os.getenv("SECURITY_EMAIL"),
}
```

Then add the variable to your `.env` file:

```env
SECURITY_EMAIL=security@example.com
```

You may also update `.env.example` so future users know this variable is required.

## Screenshots

## Future Improvements

- Request cancellation by users
- Email templates with HTML formatting
- Role-based authentication
- File attachment support
- Search and filtering
- Export reports to Excel/PDF
- Dark mode
- Docker deployment
- REST API support

## Author

Varun Chandrasekar
