#!/usr/bin/env python3
"""
Training Report Generator
Generates HTML format training and evaluation reports
"""
import os
import json
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def generate_html_report(
    metrics,
    training_info,
    data_info,
    output_path="training_reports/report.html"
):
    """
    Generate HTML training report
    
    Args:
        metrics: Evaluation metrics {mae, rmse, accuracy, threshold}
        training_info: Training info {epochs, batch_size, learning_rate, duration, best_loss}
        data_info: Data info {satellite_files, sensor_records, date_range}
        output_path: Output file path
    
    Returns:
        str: Report file path
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Load previous report (if exists) for comparison
    previous_metrics = load_previous_metrics()
    comparison_html = generate_comparison_section(metrics, previous_metrics)
    
    # Generate HTML
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Training Report - {timestamp}</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica', 'Arial', sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 20px;
                line-height: 1.6;
            }}
            
            .container {{
                max-width: 1000px;
                margin: 0 auto;
                background: white;
                border-radius: 12px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                overflow: hidden;
            }}
            
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 40px;
                text-align: center;
            }}
            
            .header h1 {{
                font-size: 2.5em;
                margin-bottom: 10px;
            }}
            
            .header .timestamp {{
                font-size: 1.1em;
                opacity: 0.9;
            }}
            
            .content {{
                padding: 40px;
            }}
            
            .section {{
                margin-bottom: 40px;
            }}
            
            .section h2 {{
                color: #667eea;
                font-size: 1.8em;
                margin-bottom: 20px;
                padding-bottom: 10px;
                border-bottom: 3px solid #667eea;
            }}
            
            .metrics-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin-top: 20px;
            }}
            
            .metric-card {{
                background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                padding: 25px;
                border-radius: 10px;
                text-align: center;
                transition: transform 0.3s;
            }}
            
            .metric-card:hover {{
                transform: translateY(-5px);
                box-shadow: 0 5px 20px rgba(0,0,0,0.1);
            }}
            
            .metric-card .label {{
                font-size: 0.9em;
                color: #666;
                text-transform: uppercase;
                letter-spacing: 1px;
                margin-bottom: 10px;
            }}
            
            .metric-card .value {{
                font-size: 2.5em;
                font-weight: bold;
                color: #667eea;
            }}
            
            .metric-card .unit {{
                font-size: 0.8em;
                color: #888;
            }}
            
            .info-table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 15px;
            }}
            
            .info-table tr {{
                border-bottom: 1px solid #eee;
            }}
            
            .info-table td {{
                padding: 12px;
            }}
            
            .info-table td:first-child {{
                font-weight: bold;
                color: #667eea;
                width: 200px;
            }}
            
            .status-badge {{
                display: inline-block;
                padding: 5px 15px;
                border-radius: 20px;
                font-size: 0.9em;
                font-weight: bold;
            }}
            
            .status-success {{
                background: #4caf50;
                color: white;
            }}
            
            .status-warning {{
                background: #ff9800;
                color: white;
            }}
            
            .comparison {{
                display: flex;
                align-items: center;
                gap: 10px;
            }}
            
            .trend-up {{
                color: #4caf50;
                font-size: 1.2em;
            }}
            
            .trend-down {{
                color: #f44336;
                font-size: 1.2em;
            }}
            
            .trend-neutral {{
                color: #999;
                font-size: 1.2em;
            }}
            
            .footer {{
                background: #f5f7fa;
                padding: 20px;
                text-align: center;
                color: #666;
                font-size: 0.9em;
            }}
            
            .recommendation {{
                background: #e3f2fd;
                border-left: 4px solid #2196f3;
                padding: 15px;
                margin-top: 20px;
                border-radius: 5px;
            }}
            
            .recommendation h3 {{
                color: #1976d2;
                margin-bottom: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🌤️ Singapore Weather AI</h1>
                <h2>Training Report</h2>
                <div class="timestamp">Generated: {timestamp}</div>
            </div>
            
            <div class="content">
                <!-- Executive Summary -->
                <div class="section">
                    <h2>📊 Executive Summary</h2>
                    <div class="metrics-grid">
                        <div class="metric-card">
                            <div class="label">MAE</div>
                            <div class="value">{metrics.get('mae', 0):.4f}</div>
                            <div class="unit">mm</div>
                        </div>
                        <div class="metric-card">
                            <div class="label">RMSE</div>
                            <div class="value">{metrics.get('rmse', 0):.4f}</div>
                            <div class="unit">mm</div>
                        </div>
                        <div class="metric-card">
                            <div class="label">Rain Detection Accuracy</div>
                            <div class="value">{metrics.get('accuracy', 0)*100:.2f}</div>
                            <div class="unit">%</div>
                        </div>
                    </div>
                </div>
                
                <!-- Performance Comparison -->
                {comparison_html}
                
                <!-- Data Overview -->
                <div class="section">
                    <h2>📁 Data Overview</h2>
                    <table class="info-table">
                        <tr>
                            <td>Satellite Files</td>
                            <td>{data_info.get('satellite_files', 'N/A')} files</td>
                        </tr>
                        <tr>
                            <td>Sensor Records</td>
                            <td>{data_info.get('sensor_records', 'N/A'):,} records</td>
                        </tr>
                        <tr>
                            <td>Date Range</td>
                            <td>{data_info.get('date_range', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td>Active Sensors</td>
                            <td>{data_info.get('num_sensors', 'N/A')} sensors</td>
                        </tr>
                    </table>
                </div>
                
                <!-- Training Details -->
                <div class="section">
                    <h2>🔧 Training Details</h2>
                    <table class="info-table">
                        <tr>
                            <td>Epochs</td>
                            <td>{training_info.get('epochs', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td>Batch Size</td>
                            <td>{training_info.get('batch_size', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td>Learning Rate</td>
                            <td>{training_info.get('learning_rate', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td>Duration</td>
                            <td>{training_info.get('duration', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td>Best Valid Loss</td>
                            <td>{training_info.get('best_loss', 'N/A'):.4f}</td>
                        </tr>
                        <tr>
                            <td>Device</td>
                            <td>{training_info.get('device', 'N/A')}</td>
                        </tr>
                    </table>
                </div>
                
                <!-- Evaluation Results -->
                <div class="section">
                    <h2>📈 Evaluation Results</h2>
                    <table class="info-table">
                        <tr>
                            <td>Rain Threshold</td>
                            <td>{metrics.get('threshold', 0.1)} mm</td>
                        </tr>
                        <tr>
                            <td>Test Samples</td>
                            <td>{metrics.get('num_samples', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td>Model Status</td>
                            <td><span class="status-badge status-success">Deployed</span></td>
                        </tr>
                    </table>
                    
                    <div class="recommendation">
                        <h3>💡 Recommendations</h3>
                        {generate_recommendations(metrics, previous_metrics)}
                    </div>
                </div>
            </div>
            
            <div class="footer">
                <p>Singapore Weather AI - Automated Training System</p>
                <p>© 2026 All Rights Reserved</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Write to file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    logger.info(f"✅ Report generated: {output_path}")
    
    # Save current metrics for next comparison
    save_current_metrics(metrics)
    
    return output_path


def generate_comparison_section(current_metrics, previous_metrics):
    """Generate performance comparison section"""
    if not previous_metrics:
        return ""
    
    def calculate_change(current, previous, reverse=False):
        """Calculate percentage change and trend"""
        if previous == 0:
            return "N/A", "neutral"
        
        change = ((current - previous) / previous) * 100
        
        # For MAE and RMSE, lower is better (reverse=True)
        if reverse:
            if change < -5:
                trend = "up"  # Improvement
            elif change > 5:
                trend = "down"  # Degradation
            else:
                trend = "neutral"
        else:
            if change > 5:
                trend = "up"
            elif change < -5:
                trend = "down"
            else:
                trend = "neutral"
        
        return f"{abs(change):.1f}%", trend
    
    mae_change, mae_trend = calculate_change(
        current_metrics.get('mae', 0),
        previous_metrics.get('mae', 0),
        reverse=True
    )
    
    rmse_change, rmse_trend = calculate_change(
        current_metrics.get('rmse', 0),
        previous_metrics.get('rmse', 0),
        reverse=True
    )
    
    acc_change, acc_trend = calculate_change(
        current_metrics.get('accuracy', 0),
        previous_metrics.get('accuracy', 0)
    )
    
    trend_icons = {
        'up': '↑',
        'down': '↓',
        'neutral': '→'
    }
    
    return f"""
    <div class="section">
        <h2>📊 Performance Comparison</h2>
        <table class="info-table">
            <tr>
                <td><strong>Metric</strong></td>
                <td><strong>Current</strong></td>
                <td><strong>Previous</strong></td>
                <td><strong>Change</strong></td>
            </tr>
            <tr>
                <td>MAE</td>
                <td>{current_metrics.get('mae', 0):.4f} mm</td>
                <td>{previous_metrics.get('mae', 0):.4f} mm</td>
                <td class="comparison">
                    <span class="trend-{mae_trend}">{trend_icons[mae_trend]} {mae_change}</span>
                </td>
            </tr>
            <tr>
                <td>RMSE</td>
                <td>{current_metrics.get('rmse', 0):.4f} mm</td>
                <td>{previous_metrics.get('rmse', 0):.4f} mm</td>
                <td class="comparison">
                    <span class="trend-{rmse_trend}">{trend_icons[rmse_trend]} {rmse_change}</span>
                </td>
            </tr>
            <tr>
                <td>Accuracy</td>
                <td>{current_metrics.get('accuracy', 0)*100:.2f}%</td>
                <td>{previous_metrics.get('accuracy', 0)*100:.2f}%</td>
                <td class="comparison">
                    <span class="trend-{acc_trend}">{trend_icons[acc_trend]} {acc_change}</span>
                </td>
            </tr>
        </table>
    </div>
    """


def generate_recommendations(current_metrics, previous_metrics):
    """Generate recommendations"""
    recommendations = []
    
    mae = current_metrics.get('mae', 0)
    accuracy = current_metrics.get('accuracy', 0)
    
    # Recommendations based on performance
    if mae > 0.5:
        recommendations.append("• MAE is high, consider adding more specific training data or adjusting architecture")
    elif mae < 0.1:
        recommendations.append("• MAE is excellent, model performance is strong")
    
    if accuracy < 0.7:
        recommendations.append("• Accuracy is low, check data quality or adjust rain threshold")
    elif accuracy > 0.9:
        recommendations.append("• Accuracy is excellent, model is ready for production")
    
    # Compare with previous training
    if previous_metrics:
        if current_metrics.get('mae', 0) > previous_metrics.get('mae', 0) * 1.1:
            recommendations.append("• ⚠️ Performance degraded compared to last training, check data quality")
        elif current_metrics.get('mae', 0) < previous_metrics.get('mae', 0) * 0.9:
            recommendations.append("• ✅ Performance significantly improved compared to last training")
    
    if not recommendations:
        recommendations.append("• Model performance is stable, continue with current strategy")
    
    return "<br>".join(recommendations)


def load_previous_metrics():
    """Load metrics from previous training"""
    metrics_file = "training_reports/latest_metrics.json"
    if os.path.exists(metrics_file):
        try:
            with open(metrics_file, 'r') as f:
                return json.load(f)
        except:
            return None
    return None


def save_current_metrics(metrics):
    """Save current metrics for next comparison"""
    os.makedirs("training_reports", exist_ok=True)
    metrics_file = "training_reports/latest_metrics.json"
    
    with open(metrics_file, 'w') as f:
        json.dump(metrics, f, indent=2)


if __name__ == "__main__":
    # Test report generation
    logging.basicConfig(level=logging.INFO)
    
    # Mock data
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
        'duration': '15m 30s',
        'best_loss': 0.0456,
        'device': 'MPS (Apple Silicon)'
    }
    
    test_data_info = {
        'satellite_files': 240,
        'sensor_records': 50000,
        'date_range': '2026-01-01 to 2026-01-20',
        'num_sensors': 61
    }
    
    report_path = generate_html_report(
        test_metrics,
        test_training_info,
        test_data_info,
        "training_reports/test_report.html"
    )
    
    print(f"\n✅ Test report generated: {report_path}")
    print("Please open in browser to check")
