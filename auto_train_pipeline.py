#!/usr/bin/env python3
"""
自动化训练流程主编排脚本
协调数据获取、训练、评估和通知的完整流程
"""
import os
import sys
import json
import logging
import subprocess
import time
from datetime import datetime, timedelta, date
from pathlib import Path
import traceback

# 导入自定义模块
from notification import send_training_success_email, send_training_failure_email
from generate_report import generate_html_report
from training_history import add_training_record, get_training_stats

# 日志配置
LOG_DIR = "training_logs"
os.makedirs(LOG_DIR, exist_ok=True)

log_file = os.path.join(LOG_DIR, f"training_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# 配置
MAX_RETRIES = 2
STATE_FILE = "training_state.json"


class TrainingPipeline:
    """自动化训练流程管理器"""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.state = self.load_state()
        self.current_step = None
        self.retry_count = 0
        
    def load_state(self):
        """加载上次训练状态"""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_state(self):
        """保存当前状态"""
        with open(STATE_FILE, 'w') as f:
            json.dump(self.state, f, indent=2, default=str)
    
    def get_last_training_date(self):
        """获取上次训练的结束日期"""
        if 'last_training_end_date' in self.state:
            return datetime.strptime(self.state['last_training_end_date'], '%Y-%m-%d').date()
        # 默认从20天前开始（如果是首次训练）
        return date.today() - timedelta(days=20)
    
    def run_command(self, cmd, step_name, timeout=3600):
        """
        运行shell命令
        
        Args:
            cmd: 命令列表或字符串
            step_name: 步骤名称
            timeout: 超时时间（秒）
        
        Returns:
            bool: 是否成功
        """
        logger.info(f"{'='*60}")
        logger.info(f"开始执行: {step_name}")
        logger.info(f"命令: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
        logger.info(f"{'='*60}")
        
        self.current_step = step_name
        
        try:
            if isinstance(cmd, str):
                cmd = cmd.split()
            
            # 🆕 添加环境变量强制无缓冲输出
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True,
                env=env  # 🆕 传递环境变量
            )
            
            logger.info(f"✅ {step_name} 完成")
            if result.stdout:
                logger.info(f"输出:\n{result.stdout}")
            
            return True
            
        except subprocess.TimeoutExpired:
            logger.error(f"❌ {step_name} 超时（{timeout}秒）")
            return False
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ {step_name} 失败")
            logger.error(f"返回码: {e.returncode}")
            if e.stdout:
                logger.error(f"标准输出:\n{e.stdout}")
            if e.stderr:
                logger.error(f"错误输出:\n{e.stderr}")
            return False
        except Exception as e:
            logger.error(f"❌ {step_name} 异常: {e}")
            logger.error(traceback.format_exc())
            return False
    
    def step_1_download_satellite_data(self):
        """步骤1: 下载卫星数据"""
        logger.info("\n📡 步骤 1/5: 下载卫星数据")
        
        # 下载最近24小时的数据
        cmd = [
            "python3", "download_jaxa_data.py",
            "--mode", "batch",
            "--hours", "24"
        ]
        
        return self.run_command(cmd, "下载卫星数据", timeout=1800)
    
    def step_2_download_sensor_data(self):
        """步骤2: 下载传感器数据（增量）"""
        logger.info("\n🌡️ 步骤 2/5: 下载传感器数据")
        
        # 计算日期范围
        last_date = self.get_last_training_date()
        start_date = last_date + timedelta(days=1)
        end_date = date.today()
        
        logger.info(f"数据范围: {start_date} 至 {end_date}")
        
        # 更新 fetch_and_process_gov_data.py 的配置
        # 这里我们需要修改脚本以支持命令行参数，或者直接修改配置
        # 为了简化，我们使用环境变量传递日期
        
        env = os.environ.copy()
        env['FETCH_START_DATE'] = start_date.isoformat()
        env['FETCH_END_DATE'] = end_date.isoformat()
        
        cmd = ["python3", "fetch_and_process_gov_data.py"]
        
        success = self.run_command(cmd, "下载传感器数据", timeout=1800)
        
        if success:
            # 更新状态
            self.state['last_training_end_date'] = end_date.isoformat()
            self.save_state()
        
        return success
    
    def step_3_preprocess_satellite_images(self):
        """步骤3: 预处理卫星图像"""
        logger.info("\n🖼️ 步骤 3/5: 预处理卫星图像")
        
        cmd = ["python3", "preprocess_images.py"]
        
        return self.run_command(cmd, "预处理卫星图像", timeout=1800)
    
    def step_4_train_model(self):
        """步骤4: 训练模型"""
        logger.info("\n🧠 步骤 4/5: 训练模型")
        
        cmd = ["python3", "train.py"]
        
        return self.run_command(cmd, "训练模型", timeout=3600)
    
    def step_5_evaluate_model(self):
        """步骤5: 评估模型"""
        logger.info("\n📊 步骤 5/5: 评估模型")
        
        cmd = ["python3", "evaluate.py"]
        
        return self.run_command(cmd, "评估模型", timeout=600)
    
    def collect_metrics(self):
        """收集评估指标"""
        logger.info("\n📈 收集评估指标...")
        
        # 从evaluate.py生成的JSON文件读取指标
        results_file = "evaluation_results.json"
        
        if os.path.exists(results_file):
            try:
                with open(results_file, 'r') as f:
                    metrics = json.load(f)
                logger.info(f"已从 {results_file} 加载评估指标")
                return metrics
            except Exception as e:
                logger.warning(f"读取评估结果失败: {e}")
        
        # 如果文件不存在，返回默认值
        logger.warning("评估结果文件不存在，使用默认值")
        return {
            'mae': 0.0,
            'rmse': 0.0,
            'accuracy': 0.0,
            'threshold': 0.1,
            'num_samples': 0
        }
    
    def collect_data_info(self):
        """收集数据信息"""
        logger.info("\n📁 收集数据信息...")
        
        # 统计卫星文件数量
        sat_dir = "satellite_data"
        sat_files = len([f for f in os.listdir(sat_dir) if f.endswith('.nc')]) if os.path.exists(sat_dir) else 0
        
        # 统计传感器记录数
        import pandas as pd
        csv_path = "real_sensor_data.csv"
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            sensor_records = len(df)
            num_sensors = df['sensor_id'].nunique() if 'sensor_id' in df.columns else 0
            date_range = f"{df['timestamp'].min()} 至 {df['timestamp'].max()}" if 'timestamp' in df.columns else "N/A"
        else:
            sensor_records = 0
            num_sensors = 0
            date_range = "N/A"
        
        return {
            'satellite_files': sat_files,
            'sensor_records': sensor_records,
            'num_sensors': num_sensors,
            'date_range': date_range
        }
    
    def collect_training_info(self):
        """收集训练信息"""
        duration = datetime.now() - self.start_time
        minutes = int(duration.total_seconds() // 60)
        seconds = int(duration.total_seconds() % 60)
        
        # 🆕 从环境变量读取实际配置
        epochs_initial = int(os.environ.get('EPOCHS_INITIAL', 30))
        epochs_incremental = int(os.environ.get('EPOCHS_INCREMENTAL', 5))
        
        # 判断是否存在模型文件来确定使用哪个epochs值
        model_exists = os.path.exists("weather_fusion_model.pth")
        actual_epochs = epochs_incremental if model_exists else epochs_initial
        
        return {
            'epochs': actual_epochs,
            'epochs_mode': '增量训练' if model_exists else '首次训练',
            'batch_size': 4,
            'learning_rate': 0.001,
            'duration': f"{minutes}分{seconds}秒",
            'best_loss': 0.0,  # 从训练日志读取
            'device': 'Auto'
        }
    
    def generate_and_send_report(self, success=True, error_message=None):
        """生成并发送报告"""
        logger.info("\n📧 生成并发送报告...")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if success:
            # 收集所有信息
            metrics = self.collect_metrics()
            data_info = self.collect_data_info()
            training_info = self.collect_training_info()
            
            # 生成报告
            report_path = f"training_reports/report_{timestamp}.html"
            report_path = generate_html_report(metrics, training_info, data_info, report_path)
            
            # 发送成功邮件
            plot_path = "evaluation_plot.png"
            send_training_success_email(report_path, plot_path, metrics)
            
        else:
            # 发送失败邮件
            send_training_failure_email(
                error_message or "未知错误",
                self.current_step or "未知步骤",
                log_file
            )
    
    def run(self):
        """运行完整流程"""
        logger.info("="*80)
        logger.info("🚀 开始自动化训练流程")
        logger.info(f"开始时间: {self.start_time}")
        logger.info("="*80)
        
        steps = [
            self.step_1_download_satellite_data,
            self.step_2_download_sensor_data,
            self.step_3_preprocess_satellite_images,
            self.step_4_train_model,
            self.step_5_evaluate_model
        ]
        
        for step_func in steps:
            success = False
            
            # 重试逻辑
            for attempt in range(MAX_RETRIES + 1):
                if attempt > 0:
                    logger.warning(f"🔄 重试 {attempt}/{MAX_RETRIES}...")
                    time.sleep(5)  # 等待5秒后重试
                
                success = step_func()
                
                if success:
                    break
            
            if not success:
                error_msg = f"步骤失败（已重试{MAX_RETRIES}次）: {step_func.__name__}"
                logger.error(f"\n❌ {error_msg}")
                logger.error("流程中止")
                
                # 发送失败通知
                self.generate_and_send_report(success=False, error_message=error_msg)
                return False
        
        # 所有步骤成功
        end_time = datetime.now()
        duration = end_time - self.start_time
        logger.info("\n" + "="*80)
        logger.info("✅ 训练流程完成！")
        logger.info(f"总耗时: {duration}")
        logger.info("="*80)
        
        # 收集信息用于历史记录
        metrics = self.collect_metrics()
        data_info = self.collect_data_info()
        training_info = self.collect_training_info()
        
        # 记录训练历史
        training_config = {
            'epochs': 30,
            'batch_size': 4,
            'learning_rate': 0.001
        }
        
        add_training_record(
            start_time=self.start_time,
            end_time=end_time,
            duration_seconds=duration.total_seconds(),
            metrics=metrics,
            data_info=data_info,
            training_config=training_config,
            success=True
        )
        
        logger.info("✅ 训练历史已记录")
        
        # 生成并发送成功报告
        self.generate_and_send_report(success=True)
        
        return True


def main():
    """主函数"""
    try:
        pipeline = TrainingPipeline()
        success = pipeline.run()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"❌ 流程异常: {e}")
        logger.error(traceback.format_exc())
        
        # 发送失败通知
        send_training_failure_email(
            str(e) + "\n\n" + traceback.format_exc(),
            "流程异常",
            log_file
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
