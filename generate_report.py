#!/usr/bin/env python3
"""
训练报告生成器
生成HTML格式的训练和评估报告
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
    生成HTML训练报告
    
    Args:
        metrics: 评估指标 {mae, rmse, accuracy, threshold}
        training_info: 训练信息 {epochs, batch_size, learning_rate, duration, best_loss}
        data_info: 数据信息 {satellite_files, sensor_records, date_range}
        output_path: 输出文件路径
    
    Returns:
        str: 报告文件路径
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # 读取历史报告（如果存在）进行对比
    previous_metrics = load_previous_metrics()
    comparison_html = generate_comparison_section(metrics, previous_metrics)
    
    # 生成HTML
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>模型训练报告 - {timestamp}</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
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
                <h1>🌤️ 新加坡天气预测模型</h1>
                <h2>训练报告</h2>
                <div class="timestamp">生成时间: {timestamp}</div>
            </div>
            
            <div class="content">
                <!-- 执行摘要 -->
                <div class="section">
                    <h2>📊 执行摘要</h2>
                    <div class="metrics-grid">
                        <div class="metric-card">
                            <div class="label">平均绝对误差</div>
                            <div class="value">{metrics.get('mae', 0):.4f}</div>
                            <div class="unit">mm</div>
                        </div>
                        <div class="metric-card">
                            <div class="label">均方根误差</div>
                            <div class="value">{metrics.get('rmse', 0):.4f}</div>
                            <div class="unit">mm</div>
                        </div>
                        <div class="metric-card">
                            <div class="label">降雨检测准确率</div>
                            <div class="value">{metrics.get('accuracy', 0)*100:.2f}</div>
                            <div class="unit">%</div>
                        </div>
                    </div>
                </div>
                
                <!-- 性能对比 -->
                {comparison_html}
                
                <!-- 数据概览 -->
                <div class="section">
                    <h2>📁 数据概览</h2>
                    <table class="info-table">
                        <tr>
                            <td>卫星数据文件</td>
                            <td>{data_info.get('satellite_files', 'N/A')} 个</td>
                        </tr>
                        <tr>
                            <td>传感器记录数</td>
                            <td>{data_info.get('sensor_records', 'N/A'):,} 条</td>
                        </tr>
                        <tr>
                            <td>数据时间范围</td>
                            <td>{data_info.get('date_range', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td>传感器数量</td>
                            <td>{data_info.get('num_sensors', 'N/A')} 个</td>
                        </tr>
                    </table>
                </div>
                
                <!-- 训练详情 -->
                <div class="section">
                    <h2>🔧 训练详情</h2>
                    <table class="info-table">
                        <tr>
                            <td>训练轮数</td>
                            <td>{training_info.get('epochs', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td>批次大小</td>
                            <td>{training_info.get('batch_size', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td>学习率</td>
                            <td>{training_info.get('learning_rate', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td>训练时长</td>
                            <td>{training_info.get('duration', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td>最佳验证损失</td>
                            <td>{training_info.get('best_loss', 'N/A'):.4f}</td>
                        </tr>
                        <tr>
                            <td>计算设备</td>
                            <td>{training_info.get('device', 'N/A')}</td>
                        </tr>
                    </table>
                </div>
                
                <!-- 评估结果 -->
                <div class="section">
                    <h2>📈 评估结果</h2>
                    <table class="info-table">
                        <tr>
                            <td>降雨阈值</td>
                            <td>{metrics.get('threshold', 0.1)} mm</td>
                        </tr>
                        <tr>
                            <td>评估样本数</td>
                            <td>{metrics.get('num_samples', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td>模型状态</td>
                            <td><span class="status-badge status-success">已部署</span></td>
                        </tr>
                    </table>
                    
                    <div class="recommendation">
                        <h3>💡 建议</h3>
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
    
    # 写入文件
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    logger.info(f"✅ 报告已生成: {output_path}")
    
    # 保存当前指标供下次对比
    save_current_metrics(metrics)
    
    return output_path


def generate_comparison_section(current_metrics, previous_metrics):
    """生成性能对比部分"""
    if not previous_metrics:
        return ""
    
    def calculate_change(current, previous, reverse=False):
        """计算变化百分比和趋势"""
        if previous == 0:
            return "N/A", "neutral"
        
        change = ((current - previous) / previous) * 100
        
        # 对于MAE和RMSE，降低是好的（reverse=True）
        if reverse:
            if change < -5:
                trend = "up"  # 改进
            elif change > 5:
                trend = "down"  # 退化
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
        <h2>📊 性能对比</h2>
        <table class="info-table">
            <tr>
                <td><strong>指标</strong></td>
                <td><strong>本次训练</strong></td>
                <td><strong>上次训练</strong></td>
                <td><strong>变化</strong></td>
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
                <td>准确率</td>
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
    """生成建议"""
    recommendations = []
    
    mae = current_metrics.get('mae', 0)
    accuracy = current_metrics.get('accuracy', 0)
    
    # 基于性能的建议
    if mae > 0.5:
        recommendations.append("• MAE较高，建议增加训练数据或调整模型架构")
    elif mae < 0.1:
        recommendations.append("• MAE表现优秀，模型性能良好")
    
    if accuracy < 0.7:
        recommendations.append("• 准确率偏低，建议检查数据质量或调整降雨阈值")
    elif accuracy > 0.9:
        recommendations.append("• 准确率优秀，模型可以投入生产使用")
    
    # 对比上次训练
    if previous_metrics:
        if current_metrics.get('mae', 0) > previous_metrics.get('mae', 0) * 1.1:
            recommendations.append("• ⚠️ 性能相比上次训练有所下降，建议检查数据质量")
        elif current_metrics.get('mae', 0) < previous_metrics.get('mae', 0) * 0.9:
            recommendations.append("• ✅ 性能相比上次训练有显著提升")
    
    if not recommendations:
        recommendations.append("• 模型性能稳定，继续保持当前训练策略")
    
    return "<br>".join(recommendations)


def load_previous_metrics():
    """加载上次训练的指标"""
    metrics_file = "training_reports/latest_metrics.json"
    if os.path.exists(metrics_file):
        try:
            with open(metrics_file, 'r') as f:
                return json.load(f)
        except:
            return None
    return None


def save_current_metrics(metrics):
    """保存当前指标供下次对比"""
    os.makedirs("training_reports", exist_ok=True)
    metrics_file = "training_reports/latest_metrics.json"
    
    with open(metrics_file, 'w') as f:
        json.dump(metrics, f, indent=2)


if __name__ == "__main__":
    # 测试报告生成
    logging.basicConfig(level=logging.INFO)
    
    # 模拟数据
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
        'duration': '15分30秒',
        'best_loss': 0.0456,
        'device': 'MPS (Apple Silicon)'
    }
    
    test_data_info = {
        'satellite_files': 240,
        'sensor_records': 50000,
        'date_range': '2026-01-01 至 2026-01-20',
        'num_sensors': 61
    }
    
    report_path = generate_html_report(
        test_metrics,
        test_training_info,
        test_data_info,
        "training_reports/test_report.html"
    )
    
    print(f"\n✅ 测试报告已生成: {report_path}")
    print("请在浏览器中打开查看效果")
