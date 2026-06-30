"""
Flask Approval Workflow System

This module contains the core application logic for a multi-stage approval
workflow. It includes:

- Application initialization
- Database models
- Authentication helpers
- Email utilities
- Request workflow management
- Reporting and analytics routes

The application is configured using values defined in ``config.py`` and
environment variables loaded from a ``.env`` file.
"""

##
# Imports
#
# Standard library imports
import secrets
import os
import random
from functools import wraps
from io import BytesIO
from datetime import datetime, timedelta
from collections import defaultdict

# Flask imports
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    flash,
    send_file,
    url_for,
)

# Flask extensions
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail, Message

# SQLAlchemy utilities
from sqlalchemy.orm import validates
from sqlalchemy.sql import func

# Third-party libraries
import matplotlib.pyplot as plt

# Application configuration
from config import Config


# ---------------------------------------------------------------------------
# Application Initialization
# ---------------------------------------------------------------------------

# Create the Flask application instance.
app = Flask("SparkProj")

# Load configuration values from config.py.
app.config.from_object(Config)

# Secret key used for securely signing session cookies.
app.secret_key = os.getenv("SECRET_KEY")


##
# Global Objects
#

# SQLAlchemy database instance.
db = SQLAlchemy(app)

# Flask-Migrate instance used for database migrations.
migrate = Migrate(app, db)

# Flask-Mail instance used to send emails.
mail = Mail(app)

# Workflow configuration loaded from Config.
TYPES = app.config["TYPES"]


def send_mail(subject, body, receivers, cc=None):
    """
    Send an email using the configured SMTP server.

    This helper function is responsible for sending all application emails,
    including:

    - OTP verification emails
    - Approval requests
    - Completion notifications
    - Rejection notifications

    Args:
        subject (str):
            Subject line of the email.

        body (str):
            Plain-text email body.

        receivers (list[str]):
            List of recipient email addresses.

        cc (list[str] | None):
            Optional list of CC recipients.

    Returns:
        None
    """

    msg = Message(
        subject=subject,
        body=body,
        recipients=receivers,
        cc=cc or [],
    )

    # Use the configured mail account as the sender.
    msg.sender = app.config["MAIL_USERNAME"]

    mail.send(msg)


def login_required(f):
    """
    Ensure that a user is authenticated before accessing a route.

    This decorator checks whether the user's email address exists in the
    current session. If not, the user is redirected to the login page.

    Args:
        f (Callable):
            Route function being decorated.

    Returns:
        Callable:
            Wrapped route function requiring authentication.
    """

    @wraps(f)
    def wrapper(*args, **kwargs):

        # Redirect unauthenticated users to the login page.
        if "email" not in session:
            return redirect(url_for("login"))

        return f(*args, **kwargs)

    return wrapper


##
# Database Models
#


class Requester(db.Model):
    """
    Represents a single workflow request.

    Each requester progresses through a configurable approval workflow
    defined in ``Config.TYPES``.

    The model stores requester details, tracks the current approval stage,
    identifies the current approver, and maintains the overall request
    status.

    Attributes:
        id:
            Primary key.

        name:
            Name of the requester.

        email:
            Email address of the requester.

        mobno:
            Mobile number.

        manager_email:
            Immediate manager responsible for first-stage approval.

        created_at:
            Timestamp when the request was created.

        updated_at:
            Timestamp automatically updated whenever the record changes.

        approval_token:
            Secure token used to generate approval links.

        request_type:
            Type of request being processed.

        current_assignee:
            Email address of the current approver.

        curr_stage_id:
            Numeric index representing the current workflow stage.

        status:
            Current request status.
    """

    __tablename__ = "requester"

    # ------------------------------------------------------------------
    # Basic requester information
    # ------------------------------------------------------------------

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False)

    email = db.Column(db.String(100), nullable=False)

    mobno = db.Column(db.String(10), nullable=False)

    manager_email = db.Column(db.String(100), nullable=False)

    # ------------------------------------------------------------------
    # Audit timestamps
    # ------------------------------------------------------------------

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=func.now(),
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Secure token used for email approval links.
    approval_token = db.Column(
        db.String(64),
        nullable=False,
        default=lambda: secrets.token_urlsafe(32),
    )

    # ------------------------------------------------------------------
    # Workflow information
    # ------------------------------------------------------------------

    request_type = db.Column(
        db.String(64),
        nullable=False,
        index=True,
    )

    current_assignee = db.Column(
        db.String(100),
        index=True,
    )

    curr_stage_id = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    @property
    def curr_stage(self):
        """
        Return the name of the current workflow stage.

        Once all configured stages have been completed, this property
        returns ``Completed``.

        Returns:
            str:
                Current workflow stage.
        """

        flow = TYPES[self.request_type]

        if self.curr_stage_id < len(flow):
            return flow[self.curr_stage_id]["stage"]

        return "Completed"

    @property
    def curr_assignee(self):
        """
        Return the email address of the current approver.

        Workflow stages may either:

        - Use a fixed email configured in Config.TYPES.
        - Use the requester's manager during the first approval stage.

        Returns:
            str | None:
                Email address of the current approver.
        """

        if self.curr_stage_id == len(TYPES[self.request_type]):
            return "Completed"

        stage = TYPES[self.request_type][self.curr_stage_id]

        # Static email configured for this stage.
        if stage.get("email"):
            return stage["email"]

        # Manager approval is dynamic.
        if stage["stage"] == "Manager approval":
            return self.manager_email

        return None

    @property
    def progress(self):
        """
        Return workflow progress as a fraction.

        Example:
            1/3
            2/3
            3/3

        Returns:
            str:
                Progress indicator.
        """

        flow = TYPES[self.request_type]

        return (
            f"{self.curr_stage_id}/{len(flow)}"
            if self.curr_stage_id < len(flow)
            else f"{len(flow)}/{len(flow)}"
        )

    # Overall request status.
    status = db.Column(
        db.String(30),
        nullable=False,
        default="Pending",
        index=True,
    )

    ##
    # Validators
    #

    @validates("email")
    def email_validator(self, key, email):
        """
        Validate requester email address.

        Raises:
            ValueError:
                If the email format is invalid.
        """

        if "@" not in email:
            raise ValueError("Invalid email")

        return email

    @validates("mobno")
    def mobno_validator(self, key, mobno):
        """
        Validate mobile number.

        The mobile number must:

        - Contain exactly 10 digits.
        - Consist only of numeric characters.
        """

        if len(mobno) != 10:
            raise ValueError("Length must be 10")

        if not mobno.isdigit():
            raise ValueError("Must have only digits")

        return mobno

    @validates("manager_email")
    def manager_email_validator(self, key, manager_email):
        """
        Validate the manager's email address.
        """

        if "@" not in manager_email:
            raise ValueError("Invalid email")

        return manager_email


class ReportLog(db.Model):
    """
    Stores the approval history for every request.

    A new log entry is created whenever a request is:

    - Created
    - Approved
    - Rejected

    These logs are later used to build reports, request timelines,
    and analytics.
    """

    __tablename__ = "report_log"

    id = db.Column(db.Integer, primary_key=True)

    requester_id = db.Column(
        db.Integer,
        db.ForeignKey("requester.id"),
        nullable=False,
    )

    # User who performed the action.
    advanced_by = db.Column(db.String(100), nullable=False)

    # Stage before approval.
    curr_stage = db.Column(db.String(100), nullable=False)

    # Stage after approval.
    next_stage = db.Column(db.String(100), nullable=False)

    # Timestamp of approval.
    advanced_at = db.Column(
        db.DateTime,
        server_default=func.now(),
        nullable=False,
    )

    # Optional comments (typically rejection reason).
    comments = db.Column(db.Text)


class LoginOTP(db.Model):
    """
    Stores temporary One-Time Passwords (OTPs) used during login.

    Each OTP is associated with an email address and is deleted after
    successful verification or expiration.
    """

    __tablename__ = "login_otp"

    # Email address requesting authentication.
    email = db.Column(
        db.String(100),
        primary_key=True,
    )

    # Six-digit OTP.
    otp = db.Column(
        db.String(6),
        nullable=False,
    )

    # Timestamp used to determine OTP expiry.
    created_at = db.Column(
        db.DateTime,
        server_default=func.now(),
        nullable=False,
    )


##
# Routes
#


@app.route("/login")
def login():
    """
    Render the login page.

    Displays the initial authentication page where users enter their
    email address to receive a One-Time Password (OTP).

    Returns:
        Response:
            Rendered login page.
    """
    return render_template("login.html")


@app.route("/send-otp", methods=["POST"])
def send_otp():
    """
    Generate and send a One-Time Password (OTP).

    This route performs the following actions:

    1. Retrieves the submitted email address.
    2. Validates that an email was provided.
    3. Removes expired OTP records.
    4. Generates a new six-digit OTP.
    5. Replaces any existing OTP for the user.
    6. Stores the new OTP in the database.
    7. Sends the OTP via email.
    8. Redirects the user to the OTP verification page.

    Returns:
        Response:
            Redirect to the login page on validation failure,
            otherwise renders the OTP verification page.
    """

    # Retrieve and sanitize the submitted email address.
    email = request.form.get("email", "").strip()

    # Ensure an email address has been provided.
    if not email:
        flash("Please enter email")
        return redirect(url_for("login"))

    # Remove OTPs that have expired (older than 10 minutes).
    LoginOTP.query.filter(
        LoginOTP.created_at < datetime.utcnow() - timedelta(minutes=10)
    ).delete()

    # Generate a random six-digit OTP.
    otp = str(random.randint(100000, 999999))

    # Remove any existing OTP for this email so only one remains valid.
    LoginOTP.query.filter_by(email=email).delete()

    # Store the newly generated OTP.
    db.session.add(LoginOTP(email=email, otp=otp))

    db.session.commit()

    # Send the OTP to the user's email address.
    send_mail("Your OTP", f"OTP: {otp}", [email])

    return render_template("verify_otp.html", email=email)


@app.route("/verify-otp", methods=["POST"])
def verify_otp():
    """
    Verify a submitted OTP and authenticate the user.

    After successful verification:

    - The user's email is stored in the session.
    - The OTP record is deleted.
    - The user's role is determined.
    - The user is redirected to the dashboard.

    Returns:
        Response:
            Redirect to the dashboard upon success, or an error
            message if the OTP is invalid or expired.
    """

    # Retrieve submitted credentials.
    email = request.form.get("email")
    otp = request.form.get("otp")

    # Look up a matching OTP record.
    record = LoginOTP.query.filter_by(email=email, otp=otp).first()

    # Reject invalid OTPs.
    if not record:
        return "Invalid OTP"

    # Reject expired OTPs.
    if datetime.utcnow() - record.created_at > timedelta(minutes=10):
        return "OTP expired"

    # Store the authenticated user's email in the session.
    session["email"] = email

    # OTPs are single-use, so remove it after successful verification.
    db.session.delete(record)
    db.session.commit()

    # Assign the appropriate user role.
    if email in app.config["ADMINS"]:
        session["role"] = "admin"
    else:
        session["role"] = "user"

    return redirect(url_for("index"))


@app.route("/")
@login_required
def index():
    """
    Display the main dashboard.

    Admin users can view every pending request, while regular users
    only see requests that they have submitted.

    Results are displayed using pagination.

    Returns:
        Response:
            Rendered dashboard page.
    """

    # Current page number for pagination.
    page = request.args.get("page", 1, type=int)

    # Administrators can view all pending requests.
    if session.get("role") == "admin":
        pagination = (
            Requester.query.filter_by(status="Pending")
            .order_by(Requester.id.desc())
            .paginate(page=page, per_page=5, error_out=False)
        )

    # Regular users only see their own pending requests.
    else:
        pagination = (
            Requester.query.filter_by(
                status="Pending",
                email=session.get("email"),
            )
            .order_by(Requester.id.desc())
            .paginate(page=page, per_page=5, error_out=False)
        )

    return render_template(
        "index.html",
        requesters=pagination.items,
        pagination=pagination,
    )


@app.route("/new")
@login_required
def new_request():
    """
    Render the request creation form.

    The available request types are loaded dynamically from the
    application configuration.

    Returns:
        Response:
            Rendered request creation page.
    """
    return render_template(
        "new_request.html",
        types=TYPES.keys(),
    )


@app.route("/create", methods=["POST"])
@login_required
def create():
    """
    Create a new approval request.

    This route:

    - Validates required form fields.
    - Prevents duplicate pending requests of the same type.
    - Creates a new Requester record.
    - Creates an initial report log entry.
    - Assigns the first approver.
    - Sends an approval email containing a secure approval link.

    Returns:
        Response:
            Redirect to the dashboard or back to the request form if
            validation fails.
    """

    # Retrieve and sanitize submitted form values.
    name = request.form.get("name", "").strip()
    man_email = request.form.get("man_email", "").strip()
    request_type = request.form.get("request_type", "").strip()
    mobno = request.form.get("mobno", "").strip()

    # Ensure all required fields have been provided.
    if not name or not man_email or not request_type or not mobno:
        flash("All fields are required")
        return redirect(url_for("new_request"))

    # Prevent users from submitting multiple pending requests of the
    # same request type.
    existing = Requester.query.filter_by(
        email=request.form.get("email"),
        request_type=request.form.get("request_type"),
        status="Pending",
    ).first()

    if existing:
        flash(f"You already have a pending {existing.request_type} request")
        return redirect(url_for("new_request"))

    # Create the request record.
    requester = Requester(
        name=request.form.get("name"),
        email=request.form.get("email"),
        mobno=request.form.get("mobno"),
        manager_email=request.form.get("man_email"),
        request_type=request.form.get("request_type"),
        curr_stage_id=0,
    )

    db.session.add(requester)

    # Flush so the requester receives a database ID before creating
    # related records.
    db.session.flush()

    # Store the email address of the current approver.
    requester.current_assignee = requester.curr_assignee

    db.session.flush()

    # Record the request creation in the audit log.
    log = ReportLog(
        requester_id=requester.id,
        advanced_by=requester.email,
        curr_stage="Created",
        next_stage=requester.curr_stage,
        comments="created",
    )

    db.session.add(log)

    db.session.commit()

    # Generate a secure approval URL containing the request ID and
    # approval token.
    review_url = url_for(
        "review",
        id=requester.id,
        token=requester.approval_token,
        _external=True,
    )

    # Notify the first approver that action is required.
    send_mail(
        "Action required",
        f"""
    {requester.name} has submitted a request for {requester.request_type}

    Click the link below to approve:

    {review_url}
    """,
        [requester.curr_assignee],
    )

    return redirect(url_for("index"))


@app.route("/review/<int:id>/<token>")
@login_required
def review(id, token):
    """
    Display the approval review page.

    Before rendering the page, the route verifies that:

    - The request exists.
    - The request has not already been completed or rejected.
    - The approval token is valid.

    Args:
        id (int):
            Request identifier.

        token (str):
            Secure approval token included in the email link.

    Returns:
        Response:
            Approval review page or an appropriate error response.
    """

    # Retrieve the requested approval record.
    requester = Requester.query.get_or_404(id)

    # Prevent duplicate approval decisions.
    if requester.status in ["Completed", "Rejected"]:
        return "Decision already recorded"

    # Validate the approval link.
    if token != requester.approval_token:
        return "Invalid approval link", 403

    return render_template(
        "review.html",
        requester=requester,
        token=token,
    )


@app.route("/decision/<int:id>/<token>", methods=["POST"])
@login_required
def decision(id, token):
    """
    Process an approval or rejection decision.

    This route is accessed when an approver submits the review form.
    Before processing the request, several validation checks are performed
    to ensure that:

    - The request exists.
    - The request has not already been processed.
    - The approval link is valid.
    - The logged-in user is the current approver.

    Depending on the submitted decision, the request is either:

    - Advanced to the next workflow stage.
    - Marked as completed.
    - Rejected.

    Every decision is recorded in the ReportLog table to provide
    a complete audit trail.

    Args:
        id (int):
            Unique identifier of the request.

        token (str):
            Secure approval token included in the approval email.

    Returns:
        Response:
            Confirmation page after successfully recording the decision.
    """

    # Retrieve the requested approval record.
    requester = Requester.query.get_or_404(id)

    # Prevent duplicate decisions.
    if requester.status in ["Completed", "Rejected"]:
        return "Decision already recorded"

    # Validate the approval link.
    if token != requester.approval_token:
        return "Invalid approval link", 403

    # Ensure only the current approver can process the request.
    if session.get("email") != requester.current_assignee:
        return "Unauthorized", 403

    # Retrieve the selected action and optional rejection reason.
    decision = request.form.get("decision")
    reason = request.form.get("reason", "").strip()

    # Rejections must include a reason.
    if decision == "reject" and not reason:
        flash("Reason for rejection is required")
        return redirect(url_for("review", id=id, token=token))

    ####################################################################
    # APPROVAL WORKFLOW
    ####################################################################

    if decision == "approve":

        # Determine the last workflow stage for this request type.
        max_stage = len(TYPES[requester.request_type]) - 1

        # Store the current stage before advancing.
        current_stage = requester.curr_stage

        # Determine the next workflow stage.
        if requester.curr_stage_id < max_stage:
            next_stage = TYPES[requester.request_type][requester.curr_stage_id + 1][
                "stage"
            ]
        else:
            next_stage = "Completed"

        # Record the approval action in the audit log.
        log = ReportLog(
            requester_id=requester.id,
            advanced_by=requester.curr_assignee,
            curr_stage=current_stage,
            next_stage=next_stage,
            comments=request.form.get("reason"),
        )

        db.session.add(log)

        # Flush to ensure the new log entry is available before
        # generating approval history.
        db.session.flush()

        # Retrieve the complete approval history for this request.
        history_logs = (
            ReportLog.query.filter_by(requester_id=requester.id)
            .order_by(ReportLog.advanced_at)
            .all()
        )

        # Build a readable approval history for inclusion in
        # notification emails.
        approval_history = "\n".join(
            f"{log.curr_stage} → {log.advanced_by} ✓" for log in history_logs
        )

        # Collect previous approvers so they can be CC'd on
        # subsequent approval emails.
        cc = list(
            {
                log.advanced_by
                for log in history_logs
                if log.advanced_by and "@" in log.advanced_by
            }
        )

        ################################################################
        # Advance to the next workflow stage.
        ################################################################

        if requester.curr_stage_id < max_stage:

            # Move the request forward.
            requester.curr_stage_id += 1

            # Generate a fresh approval token so previous links
            # become invalid.
            requester.approval_token = secrets.token_urlsafe(32)

            # Update the current assignee.
            requester.current_assignee = requester.curr_assignee

            # Generate the approval URL for the next approver.
            review_url = url_for(
                "review",
                id=requester.id,
                token=requester.approval_token,
                _external=True,
            )

            # Notify the next approver.
            send_mail(
                "Action Required",
                f"""
                Review request:

                Previous approvals:
                {approval_history}

                Current stage: {requester.curr_stage}

                {review_url}
                """,
                receivers=[requester.curr_assignee],
                cc=cc,
            )

        ################################################################
        # Final approval stage.
        ################################################################

        else:

            # Mark the workflow as completed.
            requester.status = "Completed"

            # Rotate the approval token to invalidate previous links.
            requester.approval_token = secrets.token_urlsafe(32)

            # Advance beyond the final workflow stage.
            requester.curr_stage_id += 1

            requester.current_assignee = requester.curr_assignee

            # Notify the requester that approval is complete.
            send_mail(
                "Request Approved",
                f"Your request for {requester.request_type} has been completed",
                [requester.email],
            )

    ####################################################################
    # REJECTION WORKFLOW
    ####################################################################

    else:

        # Mark the request as rejected.
        requester.status = "Rejected"

        requester.current_assignee = "Rejected"

        # Record the rejection in the audit log.
        log = ReportLog(
            requester_id=requester.id,
            advanced_by=requester.curr_assignee,
            curr_stage=requester.curr_stage,
            next_stage="Rejected",
            comments=request.form.get("reason"),
        )

        db.session.add(log)

        db.session.flush()

        # Notify the requester of the rejection and include
        # the approver's comments.
        send_mail(
            "Request rejected",
            f"""Your request for {requester.request_type} has been rejected.

Reason: {reason}""",
            [requester.email],
        )

    # Persist all workflow changes.
    db.session.commit()

    return """
    <h2>Decision Recorded</h2>
    <p>You may now close this tab.</p>
    """


@app.route("/reports")
@app.route("/reports/<status>")
@login_required
def reports(status=None):
    """
    Display approval reports.

    This page is available only to administrators and provides:

    - Overall request statistics.
    - Filtering by request status.
    - Paginated list of requests.

    Args:
        status (str | None):
            Optional request status filter.

    Returns:
        Response:
            Rendered reports page.
    """

    # Restrict access to administrators.
    if session.get("role") != "admin":
        return "Forbidden", 403

    # Calculate dashboard statistics.
    stats = {
        "total": Requester.query.count(),
        "pending": Requester.query.filter_by(status="Pending").count(),
        "completed": Requester.query.filter_by(status="Completed").count(),
        "rejected": Requester.query.filter_by(status="Rejected").count(),
        "cancelled": Requester.query.filter_by(status="Cancelled").count(),
    }

    query = Requester.query

    # Apply an optional status filter.
    if status:
        query = query.filter_by(status=status)

    page = request.args.get("page", 1, type=int)

    pagination = query.order_by(Requester.id.desc()).paginate(
        page=page,
        per_page=5,
        error_out=False,
    )

    return render_template(
        "reports.html",
        requesters=pagination.items,
        pagination=pagination,
        stats=stats,
        current_filter=status or "All",
    )


@app.route("/reports/request/<int:id>")
@login_required
def request_details(id):
    """
    Display detailed information about a request.

    The page includes:

    - Request information.
    - Workflow progress.
    - Complete approval timeline.

    Administrators can view any request, while regular users may only
    view requests they created.

    Args:
        id (int):
            Request identifier.

    Returns:
        Response:
            Rendered request details page.
    """

    requester = Requester.query.get_or_404(id)

    # Ensure users can only access their own requests.
    if session.get("role") != "admin" and requester.email != session.get("email"):
        return "Forbidden", 403

    # Retrieve the complete approval history.
    logs = (
        ReportLog.query.filter_by(requester_id=id).order_by(ReportLog.advanced_at).all()
    )

    # Retrieve the configured workflow for this request type.
    flow = TYPES[requester.request_type]

    return render_template(
        "request_details.html",
        requester=requester,
        logs=logs,
        flow=flow,
    )


@app.route("/assignee")
@login_required
def by_assignee():
    """
    Search for requests assigned to a specific approver.

    Administrators can use this feature to identify all pending requests
    currently assigned to a particular email address.

    Returns:
        Response:
            Rendered dashboard containing matching requests.
    """

    # Restrict access to administrators.
    if session.get("role") != "admin":
        return "Forbidden", 403

    email = request.args.get("assignee", "").strip()

    # Validate the supplied email.
    if not email or "@" not in email:
        flash("Enter a valid email")
        return redirect(url_for("index"))

    page = request.args.get("page", 1, type=int)

    # Retrieve all pending requests assigned to the specified approver.
    pagination = Requester.query.filter_by(
        current_assignee=email,
        status="Pending",
    ).paginate(
        page=page,
        per_page=10,
        error_out=False,
    )

    return render_template(
        "index.html",
        requesters=pagination.items,
        pagination=pagination,
        assignee=email,
    )


@app.route("/analytics")
@login_required
def analytics():
    """
    Display the analytics dashboard.

    This page provides an overview of requests grouped by request type.
    The aggregated data is used by both the summary table and the pie
    chart displayed on the analytics page.

    Only administrators are permitted to access this page.

    Returns:
        Response:
            Rendered analytics dashboard.
    """

    # Restrict access to administrators.
    if session.get("role") != "admin":
        return "Forbidden", 403

    # Count the number of requests for each request type.
    data = (
        db.session.query(Requester.request_type, db.func.count(Requester.id))
        .group_by(Requester.request_type)
        .all()
    )

    return render_template("analytics.html", data=data)


@app.route("/analytics/chart")
@login_required
def analytics_chart():
    """
    Generate a pie chart showing request distribution.

    The chart illustrates how many requests have been submitted for
    each configured request type.

    The image is generated dynamically using Matplotlib and returned
    directly to the browser.

    Returns:
        Response:
            PNG image containing the generated pie chart.
    """

    # Restrict access to administrators.
    if session.get("role") != "admin":
        return "Forbidden", 403

    # Retrieve request counts grouped by request type.
    data = (
        db.session.query(Requester.request_type, db.func.count(Requester.id))
        .group_by(Requester.request_type)
        .all()
    )

    labels = [row[0] for row in data]
    counts = [row[1] for row in data]

    # Create the chart.
    fig, ax = plt.subplots()

    ax.pie(counts, labels=labels, autopct="%1.1f%%")

    # Store the generated image in memory.
    img = BytesIO()

    plt.savefig(img, format="png", bbox_inches="tight")

    img.seek(0)

    # Free Matplotlib resources.
    plt.close()

    return send_file(img, mimetype="image/png")


@app.route("/analytics/type/<request_type>")
@login_required
def type_analytics(request_type):
    """
    Display analytics for a specific request type.

    This page provides:

    - Total requests.
    - Average request resolution time.
    - Average time spent in each workflow stage.
    - Paginated list of matching requests.

    Stage durations are calculated from the approval history stored
    in ReportLog.

    Args:
        request_type (str):
            Request type to analyse.

    Returns:
        Response:
            Rendered request-type analytics page.
    """

    # Restrict access to administrators.
    if session.get("role") != "admin":
        return "Forbidden", 403

    page = request.args.get("page", 1, type=int)

    # Paginated request list.
    pagination = (
        Requester.query.filter_by(request_type=request_type)
        .order_by(Requester.id.desc())
        .paginate(page=page, per_page=2, error_out=False)
    )

    # Retrieve every request of this type for statistical calculations.
    requests = Requester.query.filter(
        Requester.request_type == request_type, Requester.status != "Cancelled"
    ).all()

    # Stores workflow stage durations.
    stage_times = defaultdict(list)

    # Stores total request completion times.
    resolution_times = []

    for requester in requests:

        logs = (
            ReportLog.query.filter_by(requester_id=requester.id)
            .order_by(ReportLog.advanced_at)
            .all()
        )

        # Calculate total resolution time for completed requests.
        if requester.status == "Completed" and logs:
            hours = (logs[-1].advanced_at - requester.created_at).total_seconds() / 3600

            resolution_times.append(hours)

        # Calculate time spent between consecutive workflow stages.
        for i in range(len(logs) - 1):

            duration = (
                logs[i + 1].advanced_at - logs[i].advanced_at
            ).total_seconds() / 3600

            stage_times[logs[i].next_stage].append(duration)

    # Calculate the average duration for every workflow stage.
    bottlenecks = []

    for stage, durations in stage_times.items():

        bottlenecks.append(
            (
                stage,
                round(sum(durations) / len(durations), 2),
            )
        )

    # Longest stages appear first.
    bottlenecks.sort(key=lambda x: x[1], reverse=True)

    # Calculate the average request resolution time.
    avg_time = (
        round(sum(resolution_times) / len(resolution_times), 2)
        if resolution_times
        else 0
    )

    return render_template(
        "type_analytics.html",
        num_requests=pagination.total,
        requests=pagination.items,
        pagination=pagination,
        request_type=request_type,
        avg_time=avg_time,
        bottlenecks=bottlenecks,
    )


@app.route("/analytics/type/<request_type>/chart")
@login_required
def bottleneck_chart(request_type):
    """
    Generate a bottleneck analysis chart.

    For each workflow stage, the average processing time is calculated
    and displayed as a horizontal bar chart.

    This allows administrators to quickly identify stages causing the
    greatest delays.

    Args:
        request_type (str):
            Request type being analysed.

    Returns:
        Response:
            PNG image containing the generated chart.
    """

    # Restrict access to administrators.
    if session.get("role") != "admin":
        return "Forbidden", 403

    stage_times = defaultdict(list)

    # Retrieve every request belonging to the selected type.
    requesters = Requester.query.filter(
        Requester.request_type == request_type, Requester.status != "Cancelled"
    ).all()

    for requester in requesters:

        logs = (
            ReportLog.query.filter_by(requester_id=requester.id)
            .order_by(ReportLog.advanced_at)
            .all()
        )

        # Calculate the time spent between every workflow stage.
        for i in range(len(logs) - 1):

            duration = (
                logs[i + 1].advanced_at - logs[i].advanced_at
            ).total_seconds() / 3600

            stage_times[logs[i].next_stage].append(duration)

    # Compute average duration per workflow stage.
    bottlenecks = []

    for stage, durations in stage_times.items():

        bottlenecks.append(
            (
                stage,
                round(sum(durations) / len(durations), 2),
            )
        )

    # Display the slowest stages first.
    bottlenecks.sort(key=lambda x: x[1], reverse=True)

    labels = [b[0] for b in bottlenecks]
    hours = [b[1] for b in bottlenecks]

    # Create the horizontal bar chart.
    fig, ax = plt.subplots()

    ax.barh(labels, hours)

    ax.set_title(f"{request_type} Bottlenecks")

    ax.set_xlabel("Average Hours")

    # Store the generated chart in memory.
    img = BytesIO()

    plt.savefig(img, format="png", bbox_inches="tight")

    img.seek(0)

    # Release Matplotlib resources.
    plt.close()

    return send_file(img, mimetype="image/png")


@app.route("/cancel/<int:id>", methods=["POST"])
@login_required
def cancel_request(id):
    """
    Cancel a pending request.

    Only the requester who created the request can cancel it.
    Completed, rejected and already cancelled requests cannot
    be cancelled again.
    """

    requester = Requester.query.get_or_404(id)

    if requester.email != session.get("email"):
        return "Forbidden", 403

    if requester.status != "Pending":
        flash("Only pending requests can be cancelled.")
        return redirect(url_for("index"))

    requester.status = "Cancelled"
    requester.current_assignee = "Cancelled"

    db.session.add(
        ReportLog(
            requester_id=requester.id,
            advanced_by=requester.email,
            curr_stage=requester.curr_stage,
            next_stage="Cancelled",
            comments="Cancelled by requester",
        )
    )

    db.session.commit()

    flash("Request cancelled successfully.")

    return redirect(url_for("index"))


@app.route("/delete/<int:id>", methods=["POST"])
@login_required
def delete_request(id):
    """
    Permanently delete a request.

    This route is restricted to administrators.

    Before deleting the request itself, all associated ReportLog entries
    are removed to prevent orphaned records and foreign key conflicts.

    Args:
        id (int):
            Identifier of the request to delete.

    Returns:
        Response:
            Redirect to the dashboard.
    """

    # Restrict access to administrators.
    if session.get("role") != "admin":
        return "Forbidden", 403

    requester = Requester.query.get_or_404(id)

    # Delete approval history before deleting the request.
    ReportLog.query.filter_by(requester_id=requester.id).delete()

    db.session.delete(requester)

    db.session.commit()

    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    """
    Log the current user out of the application.

    All session data is cleared before redirecting the user back to
    the login page.

    Returns:
        Response:
            Redirect to the login page.
    """

    session.clear()

    return redirect(url_for("login"))


##
# Application Entry Point
#

if __name__ == "__main__":
    # Start the Flask development server.
    app.run(debug=True)
