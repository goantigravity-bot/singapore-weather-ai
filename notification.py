#!/usr/bin/env python3
"""
邮件通知系统
用于发送训练报告和失败通知
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

# 邮件配置（从环境变量读取）
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")  # Gmail App Password
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", SENDER_EMAIL)


def send_email(subject, html_body, attachments=None, is_failure=False):
    """
    发送HTML格式邮件
    
    Args:
        subject: 邮件主题
        html_body: HTML格式的邮件正文
        attachments: 附件列表 [(文件路径, 文件名), ...]
        is_failure: 是否为失败通知
    
    Returns:
        bool: 发送是否成功
    """
    # 检查配置
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        logger.error("邮件配置缺失。请设置环境变量: SENDER_EMAIL, SENDER_PASSWORD")
        logger.info("Gmail App Password 获取方式: https://myaccount.google.com/apppasswords")
        return False
    
    try:
        # 创建邮件对象
        msg = MIMEMultipart('alternative')
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECIPIENT_EMAIL
        msg['Subject'] = subject
        
        # 添加HTML正文
        html_part = MIMEText(html_body, 'html', 'utf-8')
        msg.attach(html_part)
        
        # 添加附件
        if attachments:
            for file_path, file_name in attachments:
                if not os.path.exists(file_path):
                    logger.warning(f"附件不存在，跳过: {file_path}")
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
                    logger.info(f"已添加附件: {file_name}")
        
        # 连接SMTP服务器并发送
        logger.info(f"正在连接到 {SMTP_SERVER}:{SMTP_PORT}...")
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        
        text = msg.as_string()
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, text)
        server.quit()
        
        logger.info(f"✅ 邮件发送成功: {subject}")
        return True
        
    except Exception as e:
        logger.error(f"❌ 邮件发送失败: {e}")
        return False


def send_training_success_email(report_path, plot_path, metrics):
    """
    发送训练成功通知
    
    Args:
        report_path: HTML报告路径
        plot_path: 评估图表路径
        metrics: 评估指标字典 {mae, rmse, accuracy}
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    subject = f"✅ 模型训练成功 - {timestamp}"
    
    # 读取报告内容
    if os.path.exists(report_path):
        with open(report_path, 'r', encoding='utf-8') as f:
            html_body = f.read()
    else:
        # 如果报告不存在，创建简单的HTML
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
            <h2>✅ 模型训练成功</h2>
            <p><strong>完成时间:</strong> {timestamp}</p>
            <p><strong>训练数据:</strong> {data_date}</p>
            
            <div class="metrics">
                <h3>📊 评估指标</h3>
                <ul>
                    <li><strong>MAE:</strong> {metrics.get('mae', 0):.4f} mm</li>
                    <li><strong>RMSE:</strong> {metrics.get('rmse', 0):.4f} mm</li>
                    <li><strong>Epochs:</strong> {metrics.get('epochs', 'N/A')}</li>
                </ul>
            </div>
            
            <p class="info">📈 查看更多详情: <a href="http://3.0.28.161:8000/monitor/">训练监控仪表盘</a></p>
        </body>
        </html>
        """
    
    # 准备附件
    attachments = []
    if os.path.exists(report_path):
        attachments.append((report_path, os.path.basename(report_path)))
    if os.path.exists(plot_path):
        attachments.append((plot_path, os.path.basename(plot_path)))
    
    return send_email(subject, html_body, attachments)


def send_training_failure_email(error_message, step_failed, log_path=None):
    """
    发送训练失败通知
    
    Args:
        error_message: 错误信息
        step_failed: 失败的步骤名称
        log_path: 日志文件路径（可选）
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    subject = f"❌ 模型训练失败 - {timestamp}"
    
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
        <h2>❌ 模型训练失败</h2>
        <p><strong>时间:</strong> {timestamp}</p>
        <p><strong>失败步骤:</strong> {step_failed}</p>
        
        <div class="error">
            <h3>错误信息</h3>
            <pre>{error_message}</pre>
        </div>
        
        <div class="info">
            <h3>建议操作</h3>
            <ul>
                <li>检查网络连接（FTP和API访问）</li>
                <li>验证数据文件是否完整</li>
                <li>查看完整日志文件（如有附件）</li>
                <li>手动运行失败的步骤进行调试</li>
            </ul>
        </div>
        
        <p><em>系统将在下次调度时自动重试。</em></p>
    </body>
    </html>
    """
    
    # 准备附件
    attachments = []
    if log_path and os.path.exists(log_path):
        attachments.append((log_path, os.path.basename(log_path)))
    
    return send_email(subject, html_body, attachments, is_failure=True)


if __name__ == "__main__":
    # 测试邮件发送
    logging.basicConfig(level=logging.INFO)
    
    print("测试邮件通知系统...")
    print(f"发件人: {SENDER_EMAIL}")
    print(f"收件人: {RECIPIENT_EMAIL}")
    
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print("\n❌ 请设置环境变量:")
        print("export SENDER_EMAIL='your-email@gmail.com'")
        print("export SENDER_PASSWORD='your-app-password'")
        print("\nGmail App Password 获取: https://myaccount.google.com/apppasswords")
    else:
        # 发送测试邮件
        test_html = """
        <html>
        <body>
            <h2>🧪 测试邮件</h2>
            <p>这是一封来自 Weather AI 训练系统的测试邮件。</p>
            <p>如果你收到这封邮件，说明邮件通知系统配置成功！</p>
        </body>
        </html>
        """
        
        success = send_email(
            subject="🧪 Weather AI - 邮件系统测试",
            html_body=test_html
        )
        
        if success:
            print("\n✅ 测试邮件发送成功！请检查收件箱。")
        else:
            print("\n❌ 测试邮件发送失败。请检查配置。")
