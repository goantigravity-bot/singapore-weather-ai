#!/usr/bin/env python3
"""
自动化训练系统测试脚本
验证所有组件是否正常工作
"""
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def check_environment():
    """检查环境变量"""
    logger.info("检查环境变量...")
    
    required_vars = ['SENDER_EMAIL', 'SENDER_PASSWORD']
    optional_vars = ['RECIPIENT_EMAIL', 'JAXA_USER', 'JAXA_PASS']
    
    missing = []
    for var in required_vars:
        if not os.environ.get(var):
            missing.append(var)
            logger.error(f"  ❌ {var} 未设置")
        else:
            logger.info(f"  ✅ {var} 已设置")
    
    for var in optional_vars:
        if not os.environ.get(var):
            logger.warning(f"  ⚠️  {var} 未设置（可选）")
        else:
            logger.info(f"  ✅ {var} 已设置")
    
    return len(missing) == 0

def check_files():
    """检查必要文件"""
    logger.info("\n检查必要文件...")
    
    required_files = [
        'auto_train_pipeline.py',
        'notification.py',
        'generate_report.py',
        'download_jaxa_data.py',
        'fetch_and_process_gov_data.py',
        'preprocess_images.py',
        'train.py',
        'evaluate.py',
        'weather_fusion_model.py',
        'weather_dataset.py'
    ]
    
    missing = []
    for file in required_files:
        if os.path.exists(file):
            logger.info(f"  ✅ {file}")
        else:
            logger.error(f"  ❌ {file} 不存在")
            missing.append(file)
    
    return len(missing) == 0

def check_directories():
    """检查并创建必要目录"""
    logger.info("\n检查目录...")
    
    required_dirs = [
        'training_logs',
        'training_reports',
        'satellite_data',
        'processed_images'
    ]
    
    for dir_name in required_dirs:
        if os.path.exists(dir_name):
            logger.info(f"  ✅ {dir_name}/")
        else:
            logger.warning(f"  ⚠️  {dir_name}/ 不存在，正在创建...")
            os.makedirs(dir_name, exist_ok=True)
            logger.info(f"  ✅ 已创建 {dir_name}/")
    
    return True

def test_notification():
    """测试邮件通知"""
    logger.info("\n测试邮件通知...")
    
    try:
        from notification import send_email
        
        test_html = """
        <html>
        <body>
            <h2>🧪 自动化训练系统测试</h2>
            <p>这是一封测试邮件，用于验证邮件通知系统是否正常工作。</p>
        </body>
        </html>
        """
        
        success = send_email(
            subject="🧪 Weather AI - 系统测试",
            html_body=test_html
        )
        
        if success:
            logger.info("  ✅ 邮件发送成功")
            return True
        else:
            logger.error("  ❌ 邮件发送失败")
            return False
            
    except Exception as e:
        logger.error(f"  ❌ 邮件测试异常: {e}")
        return False

def test_report_generation():
    """测试报告生成"""
    logger.info("\n测试报告生成...")
    
    try:
        from generate_report import generate_html_report
        
        test_metrics = {
            'mae': 0.1234,
            'rmse': 0.2345,
            'accuracy': 0.8765,
            'threshold': 0.1,
            'num_samples': 1000
        }
        
        test_training_info = {
            'epochs': 30,
            'batch_size': 4,
            'learning_rate': 0.001,
            'duration': '测试',
            'best_loss': 0.0456,
            'device': 'CPU'
        }
        
        test_data_info = {
            'satellite_files': 0,
            'sensor_records': 0,
            'date_range': '测试',
            'num_sensors': 0
        }
        
        report_path = generate_html_report(
            test_metrics,
            test_training_info,
            test_data_info,
            "training_reports/system_test_report.html"
        )
        
        if os.path.exists(report_path):
            logger.info(f"  ✅ 报告生成成功: {report_path}")
            return True
        else:
            logger.error("  ❌ 报告生成失败")
            return False
            
    except Exception as e:
        logger.error(f"  ❌ 报告生成异常: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试流程"""
    print("="*60)
    print("🧪 自动化训练系统 - 系统测试")
    print("="*60)
    
    results = {
        '环境变量': check_environment(),
        '必要文件': check_files(),
        '目录结构': check_directories(),
        '报告生成': test_report_generation(),
        '邮件通知': test_notification()
    }
    
    print("\n" + "="*60)
    print("📊 测试结果汇总")
    print("="*60)
    
    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{test_name:12} : {status}")
    
    all_passed = all(results.values())
    
    print("="*60)
    if all_passed:
        print("✅ 所有测试通过！系统可以正常使用。")
        print("\n下一步:")
        print("1. 运行 python3 auto_train_pipeline.py 开始训练")
        print("2. 或设置cron任务实现每日自动训练")
        print("3. 详细说明请查看 AUTO_TRAINING_README.md")
    else:
        print("❌ 部分测试失败，请检查上述错误信息。")
        print("\n常见问题:")
        print("1. 环境变量未设置 - 运行: export SENDER_EMAIL=xxx")
        print("2. 文件缺失 - 确保所有脚本文件存在")
        print("3. 邮件发送失败 - 检查Gmail App Password配置")
    print("="*60)
    
    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    main()
