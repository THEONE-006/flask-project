import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    ##
    # DB config
    #
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    print( os.getenv("DATABASE_URL"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    ##
    # mail config
    #
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")

    ##
    # Types
    #
    
    # To add new type,follow the below render_template
    
    # "Feature/tool to be requested": [
    #         {
    #             "stage": "Manager approval",       #Fixed first stage
    #             "email": None,
    #         },
    #         {
    #             "stage": "Stage 2",         
    #             "email": os.getenv("Stage 2 email"),    #add in env file
    #         },
    #         .
    #         .
    #         .
    #         {
    #             "stage": "Stage n",         
    #             "email": os.getenv("Stage n email"),    #add in env file
    #         },
    #     ]
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
    #   ADMINS
    #
    
    ADMINS=[
        "varunsc2006@gmail.com"
    ]