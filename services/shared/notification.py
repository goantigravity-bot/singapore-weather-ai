#!/usr/bin/env python3
"""
Email Notification System
Used for sending training reports and failure notifications
"""
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Email Configuration (Read from environment variables)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")  # Gmail App Password
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", SENDER_EMAIL)
# Extra recipients (comma separated), configured in .env.production: CC_EMAILS=a@x.com,b@x.com
CC_EMAILS = [e.strip() for e in os.environ.get("CC_EMAILS", "").split(",") if e.strip()]
ALL_RECIPIENTS = list(set(filter(None, [RECIPIENT_EMAIL] + CC_EMAILS)))


def send_email(subject, html_body, attachments=None, is_failure=False):
    """
    Send HTML format email
    
    Args:
        subject: Email subject
        html_body: Email body in HTML format
        attachments: List of attachments [(file_path, file_name), ...]
        is_failure: Whether this is a failure notification
    
    Returns:
        bool: Whether sending was successful
    """
    # Check configuration
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        logger.error("Email configuration missing. Please set environment variables: SENDER_EMAIL, SENDER_PASSWORD")
        logger.info("How to get Gmail App Password: https://myaccount.google.com/apppasswords")
        return False
    
    try:
        # Create email object
        msg = MIMEMultipart('alternative')
        msg['From'] = SENDER_EMAIL
        msg['To'] = ", ".join(ALL_RECIPIENTS)
        msg['Subject'] = subject
        
        # Add HTML body
        html_part = MIMEText(html_body, 'html', 'utf-8')
        msg.attach(html_part)
        
        # Add attachments
        if attachments:
            for file_path, file_name in attachments:
                if not os.path.exists(file_path):
                    logger.warning(f"Attachment not found, skipping: {file_path}")
                    continue
                    
                with open(file_path, 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename= {file_name}'
                    )
                    msg.attach(part)
                    logger.info(f"Attachment added: {file_name}")
        
        # Connect to SMTP server and send
        logger.info(f"Connecting to {SMTP_SERVER}:{SMTP_PORT}...")
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        
        text = msg.as_string()
        server.sendmail(SENDER_EMAIL, ALL_RECIPIENTS, text)
        server.quit()
        
        logger.info(f"✅ Email sent successfully: {subject}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Email sending failed: {e}")
        return False


def send_training_success_email(report_path, plot_path, metrics):
    """
    Send training success notification
    
    Args:
        report_path: Path to HTML report
        plot_path: Path to evaluation plot
        metrics: Evaluation metrics dictionary {mae, rmse, accuracy}
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    subject = f"✅ Model Training Success - {timestamp}"
    
    # Read report content
    if os.path.exists(report_path):
        with open(report_path, 'r', encoding='utf-8') as f:
            html_body = f.read()
    else:
        # If report does not exist, create simple HTML
        data_date = metrics.get('date', 'N/A')
        html_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .metrics {{ background-color: #e8f5e9; padding: 15px; border-radius: 5px; }}
                .info {{ color: #1976d2; }}
            </style>
        </head>
        <body>
            <h2>✅ Model Training Success</h2>
            <p><strong>Completion Time:</strong> {timestamp}</p>
            <p><strong>Training Data:</strong> {data_date}</p>
            
            <div class="metrics">
                <h3>📊 Evaluation Metrics</h3>
                <ul>
                    <li><strong>MAE:</strong> {metrics.get('mae', 0):.4f} mm</li>
                    <li><strong>RMSE:</strong> {metrics.get('rmse', 0):.4f} mm</li>
                    <li><strong>Epochs:</strong> {metrics.get('epochs', 'N/A')}</li>
                </ul>
            </div>
            
            <p class="info">📈 View more details: <a href="http://3.0.28.161:8000/monitor/">Training Monitor Dashboard</a></p>
        </body>
        </html>
        """
    
    # Prepare attachments
    attachments = []
    if os.path.exists(report_path):
        attachments.append((report_path, os.path.basename(report_path)))
    if os.path.exists(plot_path):
        attachments.append((plot_path, os.path.basename(plot_path)))
    
    return send_email(subject, html_body, attachments)


def send_training_failure_email(error_message, step_failed, log_path=None):
    """
    Send training failure notification
    
    Args:
        error_message: Error message
        step_failed: Name of the failed step
        log_path: Path to log file (optional)
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    subject = f"❌ Model Training Failed - {timestamp}"
    
    html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            .error {{ color: #d32f2f; background-color: #ffebee; padding: 15px; border-radius: 5px; }}
            .info {{ color: #1976d2; background-color: #e3f2fd; padding: 10px; border-radius: 5px; margin-top: 10px; }}
        </style>
    </head>
    <body>
        <h2>❌ Model Training Failed</h2>
        <p><strong>Time:</strong> {timestamp}</p>
        <p><strong>Failed Step:</strong> {step_failed}</p>
        
        <div class="error">
            <h3>Error Message</h3>
            <pre>{error_message}</pre>
        </div>
        
        <div class="info">
            <h3>Suggested Actions</h3>
            <ul>
                <li>Check network connection (FTP and API access)</li>
                <li>Verify data file integrity</li>
                <li>View full log file (if attached)</li>
                <li>Manually run the failed step for debugging</li>
            </ul>
        </div>
        
        <p><em>The system will retry automatically at the next scheduled time.</em></p>
    </body>
    </html>
    """
    
    # Prepare attachments
    attachments = []
    if log_path and os.path.exists(log_path):
        attachments.append((log_path, os.path.basename(log_path)))
    
    return send_email(subject, html_body, attachments, is_failure=True)


if __name__ == "__main__":
    # Test email sending
    logging.basicConfig(level=logging.INFO)
    
    print("Testing email notification system...")
    print(f"Sender: {SENDER_EMAIL}")
    print(f"Recipient: {RECIPIENT_EMAIL}")
    
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print("\n❌ Please set environment variables:")
        print("export SENDER_EMAIL='your-email@gmail.com'")
        print("export SENDER_PASSWORD='your-app-password'")
        print("\nGet Gmail App Password: https://myaccount.google.com/apppasswords")
    else:
        # Send test email
        test_html = """
        <html>
        <body>
            <h2>🧪 Test Email</h2>
            <p>This is a test email from the Weather AI Training System.</p>
            <p>If you receive this email, the notification system is configured correctly!</p>
        </body>
        </html>
        """
        
        success = send_email(
            subject="🧪 Weather AI - Email System Test",
            html_body=test_html
        )
        
        if success:
            print("\n✅ Test email sent successfully! Please check your inbox.")
        else:
            print("\n❌ Test email failed to send. Please check configuration.")
