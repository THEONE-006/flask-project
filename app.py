##
# Imports
#
import secrets
import os
import random
from functools import wraps
from io import BytesIO

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
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail, Message
from sqlalchemy.orm import validates
from sqlalchemy.sql import func

from datetime import datetime, timedelta
from collections import defaultdict

import matplotlib.pyplot as plt

from config import Config  # import configurations from config.py

app = Flask("SparkProj")

app.config.from_object(Config)

app.secret_key = os.getenv("SECRET_KEY")

##
# Global stuff
#

db = SQLAlchemy(app)
migrate = Migrate(app, db)
mail = Mail(app)

TYPES = app.config["TYPES"]


def send_mail(subject, body, receivers, cc=None):  # helper for sending mails

    msg = Message(subject=subject, body=body, recipients=receivers, cc=cc or [])
    msg.sender = app.config["MAIL_USERNAME"]

    mail.send(msg)


def login_required(f):

    @wraps(f)
    def wrapper(*args, **kwargs):

        if "email" not in session:
            return redirect(url_for("login"))

        return f(*args, **kwargs)

    return wrapper


##
# Database
#


class Requester(db.Model):  # main object that's gonna be in movement

    __tablename__ = "requester"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    mobno = db.Column(db.String(10), nullable=False)
    manager_email = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    approval_token = db.Column(
        db.String(64), nullable=False, default=lambda: secrets.token_urlsafe(32)
    )

    request_type = db.Column(db.String(64), nullable=False, index=True)
    current_assignee = db.Column(db.String(100), index=True)
    curr_stage_id = db.Column(db.Integer, nullable=False, default=0)

    @property
    def curr_stage(self):

        flow = TYPES[self.request_type]

        if self.curr_stage_id < len(flow):
            return flow[self.curr_stage_id]["stage"]

        return "Completed"

    @property
    def curr_assignee(self):
        if self.curr_stage_id == len(TYPES[self.request_type]):
            return "Completed"
        stage = TYPES[self.request_type][self.curr_stage_id]

        if stage.get("email"):
            return stage["email"]

        if stage["stage"] == "Manager approval":
            return self.manager_email

        return None

    @property
    def progress(self):

        flow = TYPES[self.request_type]

        return (
            f"{self.curr_stage_id}/{len(flow)}"
            if self.curr_stage_id < len(flow)
            else f"{len(flow)}/{len(flow)}"
        )

    status = db.Column(db.String(30), nullable=False, default="Pending", index=True)

    ##
    # Validators
    #

    @validates("email")
    def email_validator(self, key, email):
        if "@" not in email:
            raise ValueError("Invalid email")

        return email

    @validates("mobno")
    def mobno_validator(self, key, mobno):
        if len(mobno) != 10:
            raise ValueError("Length must be 10")

        if not mobno.isdigit():
            raise ValueError("Must have only digits")

        return mobno

    @validates("manager_email")
    def manager_email_validator(self, key, manager_email):
        if "@" not in manager_email:
            raise ValueError("Invalid email")

        return manager_email


class ReportLog(db.Model):  # to track approvals(by whom,at what time,etc,.)
    # to build reports

    __tablename__ = "report_log"

    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey("requester.id"), nullable=False)
    advanced_by = db.Column(db.String(100), nullable=False)
    curr_stage = db.Column(db.String(100), nullable=False)
    next_stage = db.Column(db.String(100), nullable=False)
    advanced_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)
    comments = db.Column(db.Text)


class LoginOTP(db.Model):  # for handling login

    __tablename__ = "login_otp"

    email = db.Column(db.String(100), primary_key=True)

    otp = db.Column(db.String(6), nullable=False)

    created_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)


##
# Routes
#
@app.route(("/login"))
def login():
    return render_template("login.html")


@app.route("/send-otp", methods=["POST"])
def send_otp():

    email = request.form.get("email", "").strip()
    if not email:
        flash("Please enter email")
        return redirect(url_for("login"))

    LoginOTP.query.filter(
        LoginOTP.created_at < datetime.utcnow() - timedelta(minutes=10)
    ).delete()

    otp = str(random.randint(100000, 999999))

    LoginOTP.query.filter_by(email=email).delete()

    db.session.add(LoginOTP(email=email, otp=otp))

    db.session.commit()
    send_mail("Your OTP", f"OTP: {otp}", [email])

    return render_template("verify_otp.html", email=email)


@app.route("/verify-otp", methods=["POST"])
def verify_otp():

    email = request.form.get("email")
    otp = request.form.get("otp")
    record = LoginOTP.query.filter_by(email=email, otp=otp).first()

    if not record:
        return "Invalid OTP"

    if datetime.utcnow() - record.created_at > timedelta(minutes=10):
        return "OTP expired"

    session["email"] = email

    db.session.delete(record)
    db.session.commit()

    if email in app.config["ADMINS"]:
        session["role"] = "admin"
    else:
        session["role"] = "user"

    return redirect(url_for("index"))


@app.route("/")
@login_required
def index():

    page = request.args.get("page", 1, type=int)

    if session.get("role") == "admin":
        pagination = (
            Requester.query.filter_by(status="Pending")
            .order_by(Requester.id.desc())
            .paginate(page=page, per_page=5, error_out=False)
        )

    else:
        pagination = (
            Requester.query.filter_by(status="Pending", email=session.get("email"))
            .order_by(Requester.id.desc())
            .paginate(page=page, per_page=5, error_out=False)
        )

    return render_template(
        "index.html", requesters=pagination.items, pagination=pagination
    )


@app.route("/new")
@login_required
def new_request():
    return render_template("new_request.html", types=TYPES.keys())


@app.route("/create", methods=["POST"])
@login_required
def create():
    name = request.form.get("name", "").strip()
    man_email = request.form.get("man_email", "").strip()
    request_type = request.form.get("request_type", "").strip()
    mobno = request.form.get("mobno", "").strip()

    if not name or not man_email or not request_type or not mobno:
        flash("All fields are required")
        return redirect(url_for("new_request"))

    existing = Requester.query.filter_by(
        email=request.form.get("email"),
        request_type=request.form.get("request_type"),
        status="Pending",
    ).first()

    if existing:
        flash(f"You already have a pending {existing.request_type} request")
        return redirect(url_for("new_request"))

    requester = Requester(
        name=request.form.get("name"),
        email=request.form.get("email"),
        mobno=request.form.get("mobno"),
        manager_email=request.form.get("man_email"),
        request_type=request.form.get("request_type"),
        curr_stage_id=0,
    )
    db.session.add(requester)
    db.session.flush()
    requester.current_assignee = requester.curr_assignee

    db.session.flush()

    log = ReportLog(
        requester_id=requester.id,
        advanced_by=requester.email,
        curr_stage="Created",
        next_stage=requester.curr_stage,
        comments="created",
    )

    db.session.add(log)
    db.session.commit()

    review_url = url_for(
        "review", id=requester.id, token=requester.approval_token, _external=True
    )

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

    requester = Requester.query.get_or_404(id)

    if requester.status in ["Completed", "Rejected"]:
        return "Decision already recorded"

    if token != requester.approval_token:
        return "Invalid approval link", 403

    return render_template("review.html", requester=requester, token=token)


@app.route("/decision/<int:id>/<token>", methods=["POST"])
@login_required
def decision(id, token):

    requester = Requester.query.get_or_404(id)

    if requester.status in ["Completed", "Rejected"]:
        return "Decision already recorded"

    if token != requester.approval_token:
        return "Invalid approval link", 403

    if session.get("email") != requester.current_assignee:
        return "Unauthorized", 403

    decision = request.form.get("decision")

    reason = request.form.get("reason", "").strip()

    if decision == "reject" and not reason:
        flash("Reason for rejection is required")
        return redirect(url_for("review",id=id,token=token))

    if decision == "approve":

        max_stage = len(TYPES[requester.request_type]) - 1

        current_stage = requester.curr_stage
        if requester.curr_stage_id < max_stage:
            next_stage = TYPES[requester.request_type][requester.curr_stage_id + 1][
                "stage"
            ]
        else:
            next_stage = "Completed"

        log = ReportLog(
            requester_id=requester.id,
            advanced_by=requester.curr_assignee,
            curr_stage=current_stage,
            next_stage=next_stage,
            comments=request.form.get("reason"),
        )

        db.session.add(log)
        db.session.flush()

        history_logs = (
            ReportLog.query.filter_by(requester_id=requester.id)
            .order_by(ReportLog.advanced_at)
            .all()
        )

        approval_history = "\n".join(
            f"{log.curr_stage} → {log.advanced_by} ✓" for log in history_logs
        )

        cc = list(
            {
                log.advanced_by
                for log in history_logs
                if log.advanced_by and "@" in log.advanced_by
            }
        )

        if requester.curr_stage_id < max_stage:

            requester.curr_stage_id += 1

            requester.approval_token = secrets.token_urlsafe(32)
            requester.current_assignee = requester.curr_assignee

            review_url = url_for(
                "review",
                id=requester.id,
                token=requester.approval_token,
                _external=True,
            )
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

        else:
            requester.status = "Completed"
            requester.approval_token = secrets.token_urlsafe(32)
            requester.curr_stage_id += 1
            requester.current_assignee = requester.curr_assignee

            send_mail(
                "Request Approved",
                f"""Your request for {requester.request_type} has been completed""",
                [requester.email],
            )
    else:
        requester.status = "Rejected"
        requester.current_assignee = "Rejected"

        log = ReportLog(
            requester_id=requester.id,
            advanced_by=requester.curr_assignee,
            curr_stage=requester.curr_stage,
            next_stage="Rejected",
            comments=request.form.get("reason"),
        )

        db.session.add(log)
        db.session.flush()

        send_mail(
            "Request rejected",
            f"""Your request for {requester.request_type} has been rejected.
                    Reason: {reason}""",  #### add reason from comment from form
            [requester.email],
        )

    db.session.commit()
    return """
    <h2>Decision Recorded</h2>
    <p>You may now close this tab.</p>
    """


@app.route("/reports")
@app.route("/reports/<status>")
@login_required
def reports(status=None):

    if session.get("role") != "admin":
        return "Forbidden", 403

    stats = {
        "total": Requester.query.count(),
        "pending": Requester.query.filter_by(status="Pending").count(),
        "completed": Requester.query.filter_by(status="Completed").count(),
        "rejected": Requester.query.filter_by(status="Rejected").count(),
    }

    query = Requester.query

    if status:
        query = query.filter_by(status=status)

    page = request.args.get("page", 1, type=int)

    pagination = query.order_by(Requester.id.desc()).paginate(
        page=page, per_page=5, error_out=False
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

    requester = Requester.query.get_or_404(id)

    if session.get("role") != "admin" and requester.email != session.get("email"):
        return "Forbidden", 403

    logs = (
        ReportLog.query.filter_by(requester_id=id).order_by(ReportLog.advanced_at).all()
    )
    flow = TYPES[requester.request_type]
    return render_template(
        "request_details.html", requester=requester, logs=logs, flow=flow
    )


@app.route("/assignee")
@login_required
def by_assignee():

    if session.get("role") != "admin":
        return "Forbidden", 403

    email = request.args.get("assignee", "").strip()

    if not email or "@" not in email:
        flash("Enter a valid email")

        return redirect(url_for("index"))

    page = request.args.get("page", 1, type=int)

    pagination = Requester.query.filter_by(
        current_assignee=email, status="Pending"
    ).paginate(page=page, per_page=10, error_out=False)

    return render_template(
        "index.html", requesters=pagination.items, pagination=pagination, assignee=email
    )


@app.route("/analytics")
@login_required
def analytics():

    if session.get("role") != "admin":
        return "Forbidden", 403

    data = (
        db.session.query(Requester.request_type, db.func.count(Requester.id))
        .group_by(Requester.request_type)
        .all()
    )

    return render_template("analytics.html", data=data)


@app.route("/analytics/chart")
@login_required
def analytics_chart():

    if session.get("role") != "admin":
        return "Forbidden", 403

    data = (
        db.session.query(Requester.request_type, db.func.count(Requester.id))
        .group_by(Requester.request_type)
        .all()
    )

    labels = [row[0] for row in data]
    counts = [row[1] for row in data]

    fig, ax = plt.subplots()

    ax.pie(counts, labels=labels, autopct="%1.1f%%")

    img = BytesIO()

    plt.savefig(img, format="png", bbox_inches="tight")

    img.seek(0)

    plt.close()

    return send_file(img, mimetype="image/png")


@app.route("/analytics/type/<request_type>")
@login_required
def type_analytics(request_type):

    if session.get("role") != "admin":
        return "Forbidden", 403

    page = request.args.get("page", 1, type=int)

    pagination = (
        Requester.query.filter_by(request_type=request_type)
        .order_by(Requester.id.desc())
        .paginate(page=page, per_page=2, error_out=False)
    )

    requests = Requester.query.filter_by(request_type=request_type).all()

    stage_times = defaultdict(list)
    resolution_times = []

    for requester in requests:

        logs = (
            ReportLog.query.filter_by(requester_id=requester.id)
            .order_by(ReportLog.advanced_at)
            .all()
        )

        if requester.status == "Completed" and logs:
            hours = (logs[-1].advanced_at - requester.created_at).total_seconds() / 3600

            resolution_times.append(hours)

        for i in range(len(logs) - 1):

            duration = (
                logs[i + 1].advanced_at - logs[i].advanced_at
            ).total_seconds() / 3600

            stage_times[logs[i].next_stage].append(duration)

    bottlenecks = []

    for stage, durations in stage_times.items():

        bottlenecks.append((stage, round(sum(durations) / len(durations), 2)))

    bottlenecks.sort(key=lambda x: x[1], reverse=True)

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

    if session.get("role") != "admin":
        return "Forbidden", 403

    stage_times = defaultdict(list)

    requesters = Requester.query.filter_by(request_type=request_type).all()

    for requester in requesters:
        logs = (
            ReportLog.query.filter_by(requester_id=requester.id)
            .order_by(ReportLog.advanced_at)
            .all()
        )

        for i in range(len(logs) - 1):
            duration = (
                logs[i + 1].advanced_at - logs[i].advanced_at
            ).total_seconds() / 3600

            stage_times[logs[i].next_stage].append(duration)

    bottlenecks = []

    for stage, durations in stage_times.items():

        bottlenecks.append((stage, round(sum(durations) / len(durations), 2)))

    bottlenecks.sort(key=lambda x: x[1], reverse=True)

    labels = [b[0] for b in bottlenecks]
    hours = [b[1] for b in bottlenecks]

    fig, ax = plt.subplots()

    ax.barh(labels, hours)

    ax.set_title(f"{request_type} Bottlenecks")

    ax.set_xlabel("Average Hours")

    img = BytesIO()

    plt.savefig(img, format="png", bbox_inches="tight")

    img.seek(0)

    plt.close()

    return send_file(img, mimetype="image/png")


@app.route("/delete/<int:id>", methods=["POST"])
@login_required
def delete_request(id):

    if session.get("role") != "admin":
        return "Forbidden", 403

    requester = Requester.query.get_or_404(id)

    ReportLog.query.filter_by(
        requester_id=requester.id
    ).delete()  # delete logs so that reference is broken

    db.session.delete(requester)
    db.session.commit()

    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


##
# Running
#

if __name__ == "__main__":
    app.run(debug=True)
