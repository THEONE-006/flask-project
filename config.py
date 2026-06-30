"""
Configuration module for the Request Approval Workflow application.

This module centralizes all configurable settings used throughout the
application, including:

- Database configuration
- Mail server configuration
- Workflow definitions
- Administrator accounts

Environment variables are loaded from the project's `.env` file using
python-dotenv.
"""

import os
from dotenv import load_dotenv

# Load all environment variables from the .env file.
load_dotenv()


class Config:
    """
    Application configuration.

    Flask loads this class during startup using:

        app.config.from_object(Config)

    All values defined here become available through:

        app.config["SETTING_NAME"]
    """

    ##
    # Database Configuration
    #
    # SQLAlchemy connection string used to connect to the application's
    # database.
    #
    # Example:
    # DATABASE_URL=sqlite:///requests.db
    #
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")

    # Disable SQLAlchemy's modification tracking to reduce unnecessary
    # memory usage.
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    ##
    # Mail Configuration
    #
    # Gmail SMTP settings used for:
    #
    # • Login OTP emails
    # • Approval requests
    # • Approval notifications
    # • Rejection notifications
    #
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True

    # Credentials loaded from the environment.
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")

    ##
    # Workflow Definitions
    #
    # Every request type follows a predefined approval workflow.
    #
    # Each workflow is represented as a list of stages.
    #
    # The first stage MUST always be:
    #
    #     Manager approval
    #
    # because its approver is supplied dynamically by the requester.
    #
    # Every subsequent stage should specify the email address of the
    # person or team responsible for that approval.
    #
    # To add a new request type, follow the template below:
    #
    # "Feature/tool to be requested": [
    #     {
    #         "stage": "Manager approval",
    #         "email": None,
    #     },
    #     {
    #         "stage": "Stage 2",
    #         "email": os.getenv("STAGE2_EMAIL"),
    #     },
    #     {
    #         "stage": "Stage 3",
    #         "email": os.getenv("STAGE3_EMAIL"),
    #     },
    # ]
    #
    # Every email used here should also be added to .env.example.
    #
    TYPES = {

        "WhatsApp": [
            {
                "stage": "Manager approval",
                "email": None,
            },
            {
                "stage": "Cooby approval",
                "email": os.getenv("COOBY_EMAIL"),
            },
            {
                "stage": "Help-desk",
                "email": os.getenv("HELPDESK_EMAIL"),
            },
        ],

        "AI_tools": [
            {
                "stage": "Manager approval",
                "email": None,
            },
            {
                "stage": "Cooby approval",
                "email": os.getenv("COOBY_EMAIL"),
            },
            {
                "stage": "L3",
                "email": os.getenv("HELPDESK_EMAIL"),
            },
            {
                "stage": "Help-desk",
                "email": os.getenv("HELPDESK_EMAIL"),
            },
        ],

        "3rd tool": [
            {
                "stage": "Manager approval",
                "email": None,
            },
            {
                "stage": "Cooby approval",
                "email": os.getenv("COOBY_EMAIL"),
            },
            {
                "stage": "L3",
                "email": os.getenv("HELPDESK_EMAIL"),
            },
            {
                "stage": "L4",
                "email": os.getenv("HELPDESK_EMAIL"),
            },
            {
                "stage": "Help-desk",
                "email": os.getenv("HELPDESK_EMAIL"),
            },
        ],
    }

    ##
    # Administrator Accounts
    #
    # Users whose email addresses appear in the ADMINS environment
    # variable receive administrator privileges after successful OTP
    # verification.
    #
    # Example:
    #
    # ADMINS=admin1@example.com,admin2@example.com
    #
    # Multiple email addresses should be separated by commas.
    #
    ADMINS = [
        email.strip()
        for email in os.getenv("ADMINS", "").split(",")
        if email.strip()
    ]