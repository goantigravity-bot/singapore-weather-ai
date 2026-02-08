#!/usr/bin/env python3
"""
Automated Training Pipeline Orchestrator
Coordinates the full process of data fetching, training, evaluation, and notification
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

# Import custom modules
from notification import send_training_success_email, send_training_failure_email
from generate_report import generate_html_report
from training_history import add_training_record, get_training_stats

# Logging configuration
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

# Configuration
MAX_RETRIES = 2
STATE_FILE = "training_state.json"


class TrainingPipeline:
    """Automated Training Pipeline Manager"""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.state = self.load_state()
        self.current_step = None
        self.retry_count = 0
        
    def load_state(self):
        """Load last training state"""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_state(self):
        """Save current state"""
        with open(STATE_FILE, 'w') as f:
            json.dump(self.state, f, indent=2, default=str)
    
    def get_last_training_date(self):
        """Get end date of last training"""
        if 'last_training_end_date' in self.state:
            return datetime.strptime(self.state['last_training_end_date'], '%Y-%m-%d').date()
        # Default to 20 days ago (if first run)
        return date.today() - timedelta(days=20)
    
    def run_command(self, cmd, step_name, timeout=3600):
        """
        Run shell command
        
        Args:
            cmd: Command list or string
            step_name: Name of the step
            timeout: Timeout in seconds
        
        Returns:
            bool: Success status
        """
        logger.info(f"{'='*60}")
        logger.info(f"Starting: {step_name}")
        logger.info(f"Command: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
        logger.info(f"{'='*60}")
        
        self.current_step = step_name
        
        try:
            if isinstance(cmd, str):
                cmd = cmd.split()
            
            # 🆕 Force unbuffered output
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True,
                env=env
            )
            
            logger.info(f"✅ {step_name} Completed")
            if result.stdout:
                logger.info(f"Output:\n{result.stdout}")
            
            return True
            
        except subprocess.TimeoutExpired:
            logger.error(f"❌ {step_name} Timed out ({timeout}s)")
            return False
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ {step_name} Failed")
            logger.error(f"Return Code: {e.returncode}")
            if e.stdout:
                logger.error(f"Stdout:\n{e.stdout}")
            if e.stderr:
                logger.error(f"Stderr:\n{e.stderr}")
            return False
        except Exception as e:
            logger.error(f"❌ {step_name} Exception: {e}")
            logger.error(traceback.format_exc())
            return False
    
    def step_1_download_satellite_data(self):
        """Step 1: Download Satellite Data"""
        logger.info("\n📡 Step 1/5: Download Satellite Data")
        
        # Download last 24 hours
        cmd = [
            "python3", "download_jaxa_data.py",
            "--mode", "batch",
            "--hours", "24"
        ]
        
        return self.run_command(cmd, "Download Satellite Data", timeout=1800)
    
    def step_2_download_sensor_data(self):
        """Step 2: Download Sensor Data (Incremental)"""
        logger.info("\n🌡️ Step 2/5: Download Sensor Data")
        
        # Calculate date range
        last_date = self.get_last_training_date()
        start_date = last_date + timedelta(days=1)
        end_date = date.today()
        
        logger.info(f"Date Range: {start_date} to {end_date}")
        
        env = os.environ.copy()
        env['FETCH_START_DATE'] = start_date.isoformat()
        env['FETCH_END_DATE'] = end_date.isoformat()
        
        cmd = ["python3", "fetch_and_process_gov_data.py"]
        
        success = self.run_command(cmd, "Download Sensor Data", timeout=1800)
        
        if success:
            # Update state
            self.state['last_training_end_date'] = end_date.isoformat()
            self.save_state()
        
        return success
    
    def step_3_preprocess_satellite_images(self):
        """Step 3: Preprocess Satellite Images"""
        logger.info("\n🖼️ Step 3/5: Preprocess Satellite Images")
        
        cmd = ["python3", "preprocess_images.py"]
        
        return self.run_command(cmd, "Preprocess Satellite Images", timeout=1800)
    
    def step_4_train_model(self):
        """Step 4: Train Model"""
        logger.info("\n🧠 Step 4/5: Train Model")
        
        cmd = ["python3", "train.py"]
        
        return self.run_command(cmd, "Train Model", timeout=3600)
    
    def step_5_evaluate_model(self):
        """Step 5: Evaluate Model"""
        logger.info("\n📊 Step 5/5: Evaluate Model")
        
        cmd = ["python3", "evaluate.py"]
        
        return self.run_command(cmd, "Evaluate Model", timeout=600)
    
    def collect_metrics(self):
        """Collect evaluation metrics"""
        logger.info("\n📈 Collecting metrics...")
        
        results_file = "evaluation_results.json"
        
        if os.path.exists(results_file):
            try:
                with open(results_file, 'r') as f:
                    metrics = json.load(f)
                logger.info(f"Metrics loaded from {results_file}")
                return metrics
            except Exception as e:
                logger.warning(f"Failed to read evaluation results: {e}")
        
        logger.warning("Evaluation results file not found, using defaults")
        return {
            'mae': 0.0,
            'rmse': 0.0,
            'accuracy': 0.0,
            'threshold': 0.1,
            'num_samples': 0
        }
    
    def collect_data_info(self):
        """Collect data information"""
        logger.info("\n📁 Collecting data info...")
        
        sat_dir = "satellite_data"
        sat_files = len([f for f in os.listdir(sat_dir) if f.endswith('.nc')]) if os.path.exists(sat_dir) else 0
        
        import pandas as pd
        csv_path = "real_sensor_data.csv"
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            sensor_records = len(df)
            num_sensors = df['sensor_id'].nunique() if 'sensor_id' in df.columns else 0
            date_range = f"{df['timestamp'].min()} to {df['timestamp'].max()}" if 'timestamp' in df.columns else "N/A"
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
        """Collect training information"""
        duration = datetime.now() - self.start_time
        minutes = int(duration.total_seconds() // 60)
        seconds = int(duration.total_seconds() % 60)
        
        epochs_initial = int(os.environ.get('EPOCHS_INITIAL', 30))
        epochs_incremental = int(os.environ.get('EPOCHS_INCREMENTAL', 5))
        
        model_exists = os.path.exists("weather_fusion_model.pth")
        actual_epochs = epochs_incremental if model_exists else epochs_initial
        
        return {
            'epochs': actual_epochs,
            'epochs_mode': 'Incremental' if model_exists else 'Initial',
            'batch_size': 4,
            'learning_rate': 0.001,
            'duration': f"{minutes}m {seconds}s",
            'best_loss': 0.0,  # Read from log if implemented
            'device': 'Auto'
        }
    
    def generate_and_send_report(self, success=True, error_message=None):
        """Generate and send report"""
        logger.info("\n📧 Generating and sending report...")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if success:
            metrics = self.collect_metrics()
            data_info = self.collect_data_info()
            training_info = self.collect_training_info()
            
            report_path = f"training_reports/report_{timestamp}.html"
            report_path = generate_html_report(metrics, training_info, data_info, report_path)
            
            plot_path = "evaluation_plot.png"
            send_training_success_email(report_path, plot_path, metrics)
            
        else:
            send_training_failure_email(
                error_message or "Unknown Error",
                self.current_step or "Unknown Step",
                log_file
            )
    
    def run(self):
        """Run full pipeline"""
        logger.info("="*80)
        logger.info("🚀 Starting Automated Training Pipeline")
        logger.info(f"Start Time: {self.start_time}")
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
            
            for attempt in range(MAX_RETRIES + 1):
                if attempt > 0:
                    logger.warning(f"🔄 Retry {attempt}/{MAX_RETRIES}...")
                    time.sleep(5)
                
                success = step_func()
                
                if success:
                    break
            
            if not success:
                error_msg = f"Step Failed (Retried {MAX_RETRIES} times): {step_func.__name__}"
                logger.error(f"\n❌ {error_msg}")
                logger.error("Pipeline Aborted")
                
                self.generate_and_send_report(success=False, error_message=error_msg)
                return False
        
        end_time = datetime.now()
        duration = end_time - self.start_time
        logger.info("\n" + "="*80)
        logger.info("✅ Training Pipeline Completed!")
        logger.info(f"Total Duration: {duration}")
        logger.info("="*80)
        
        metrics = self.collect_metrics()
        data_info = self.collect_data_info()
        training_info = self.collect_training_info()
        
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
        
        logger.info("✅ Training history recorded")
        
        self.generate_and_send_report(success=True)
        
        return True


def main():
    """Main function"""
    try:
        pipeline = TrainingPipeline()
        success = pipeline.run()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"❌ Pipeline Exception: {e}")
        logger.error(traceback.format_exc())
        
        send_training_failure_email(
            str(e) + "\n\n" + traceback.format_exc(),
            "Pipeline Exception",
            log_file
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
