#!/usr/bin/env python3
"""
Mibao Family Contribution Stats Generator
生成咪咪一家的 GitHub 贡献统计和可视化图表
"""

import os
import json
import requests
from datetime import datetime, timedelta
from collections import defaultdict
import subprocess

def get_github_contributions(username, token=None):
    """获取用户的 GitHub 贡献数据"""
    # 使用 GitHub GraphQL API 获取贡献数据
    query = """
    query($username: String!) {
      user(login: $username) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
                color
              }
            }
          }
        }
      }
    }
    """
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    } if token else {}
    
    response = requests.post(
        "https://api.github.com/graphql",
        json={"query": query, "variables": {"username": username}},
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        return data.get("data", {}).get("user", {}).get("contributionsCollection", {}).get("contributionCalendar", {})
    return {}

def get_commits_by_email(repo, email, since=None, until=None):
    """获取特定邮箱在仓库中的提交"""
    try:
        cmd = ["git", "log", "--author", email, "--format=%H|%ai|%s"]
        if since:
            cmd.extend(["--since", since])
        if until:
            cmd.extend(["--until", until])
        
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo if os.path.exists(repo) else ".")
        
        commits = []
        for line in result.stdout.strip().split('\n'):
            if '|' in line:
                parts = line.split('|', 2)
                if len(parts) >= 2:
                    commits.append({
                        "hash": parts[0],
                        "date": parts[1][:10],  # YYYY-MM-DD
                        "message": parts[2] if len(parts) > 2 else ""
                    })
        return commits
    except Exception as e:
        print(f"Error getting commits: {e}")
        return []

def generate_contribution_heatmap(contributions_data, title="Mibao Family Contributions"):
    """生成 SVG 贡献热力图"""
    # 创建简单的 SVG 热力图
    weeks = contributions_data.get("weeks", [])
    
    svg_width = 828
    svg_height = 128
    cell_size = 10
    cell_gap = 2
    
    colors = {
        0: "#ebedf0",   # 无贡献
        1: "#9be9a8",   # 低
        2: "#40c463",   # 中
        3: "#30a14e",   # 高
        4: "#216e39"    # 很高
    }
    
    svg_parts = [
        f'<svg width="{svg_width}" height="{svg_height}" xmlns="http://www.w3.org/2000/svg">',
        f'<text x="10" y="20" font-family="Arial" font-size="14" fill="#24292f">{title}</text>',
        '<g transform="translate(10, 35)">'
    ]
    
    for week_idx, week in enumerate(weeks):
        for day_idx, day in enumerate(week.get("contributionDays", [])):
            count = day.get("contributionCount", 0)
            color = day.get("color", colors[0])
            
            x = week_idx * (cell_size + cell_gap)
            y = day_idx * (cell_size + cell_gap)
            
            svg_parts.append(
                f'<rect x="{x}" y="{y}" width="{cell_size}" height="{cell_size}" '
                f'fill="{color}" rx="2"/>'
            )
    
    svg_parts.extend([
        '</g>',
        '</svg>'
    ])
    
    return '\n'.join(svg_parts)

def generate_stats_summary(baobao_commits, sanbao_commits):
    """生成统计摘要"""
    today = datetime.now()
    last_year = today - timedelta(days=365)
    
    # 统计最近一年的数据
    baobao_recent = [c for c in baobao_commits if c["date"] >= last_year.strftime("%Y-%m-%d")]
    sanbao_recent = [c for c in sanbao_commits if c["date"] >= last_year.strftime("%Y-%m-%d")]
    
    # 按日期统计
    daily_counts = defaultdict(lambda: {"baobao": 0, "sanbao": 0})
    
    for commit in baobao_recent:
        daily_counts[commit["date"]]["baobao"] += 1
    
    for commit in sanbao_recent:
        daily_counts[commit["date"]]["sanbao"] += 1
    
    total_baobao = len(baobao_recent)
    total_sanbao = len(sanbao_recent)
    total = total_baobao + total_sanbao
    
    return {
        "total_commits": total,
        "baobao_commits": total_baobao,
        "sanbao_commits": total_sanbao,
        "daily_breakdown": dict(daily_counts),
        "stats": {
            "baobao_percentage": round(total_baobao / total * 100, 1) if total > 0 else 0,
            "sanbao_percentage": round(total_sanbao / total * 100, 1) if total > 0 else 0,
            "current_streak": calculate_streak(daily_counts),
            "max_streak": calculate_max_streak(daily_counts)
        }
    }

def calculate_streak(daily_counts):
    """计算当前连续贡献天数"""
    today = datetime.now()
    streak = 0
    
    for i in range(365):
        date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        if date in daily_counts and (daily_counts[date]["baobao"] + daily_counts[date]["sanbao"]) > 0:
            streak += 1
        elif i > 0:  # 跳过今天（今天还没过完）
            break
    
    return streak

def calculate_max_streak(daily_counts):
    """计算最大连续贡献天数"""
    if not daily_counts:
        return 0
    
    sorted_dates = sorted(daily_counts.keys())
    max_streak = 0
    current_streak = 0
    prev_date = None
    
    for date_str in sorted_dates:
        current = datetime.strptime(date_str, "%Y-%m-%d")
        
        if prev_date and (current - prev_date).days == 1:
            current_streak += 1
        else:
            current_streak = 1
        
        max_streak = max(max_streak, current_streak)
        prev_date = current
    
    return max_streak

def main():
    """主函数"""
    print("🐱 Generating Mibao Family Contribution Stats...")
    
    # 配置
    BAOBAO_EMAIL = "1063037668@qq.com"  # 全全咪的邮箱
    SANBAO_EMAIL = "Mibao0211@163.com"  # 三宝的邮箱
    BAOBAO_REPO = "/Users/mimi/.openclaw"  # 本地仓库路径
    
    # 获取过去一年的提交
    since = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    
    # 获取爸宝的提交
    print("📊 Fetching Baobao's commits...")
    baobao_commits = get_commits_by_email(BAOBAO_REPO, BAOBAO_EMAIL, since=since)
    
    # 获取三宝的提交（从同一仓库或其他仓库）
    print("📊 Fetching Sanbao's commits...")
    sanbao_commits = get_commits_by_email(BAOBAO_REPO, SANBAO_EMAIL, since=since)
    
    # 生成统计
    stats = generate_stats_summary(baobao_commits, sanbao_commits)
    
    # 保存 JSON 数据
    with open("stats/contributions.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    # 生成简化的贡献日历数据（模拟 GitHub 格式）
    calendar_data = generate_mock_calendar_data(stats["daily_breakdown"])
    
    # 生成 SVG 图表
    svg_content = generate_contribution_heatmap(calendar_data, "🐱 Mibao Family Contributions")
    with open("stats/contributions.svg", "w", encoding="utf-8") as f:
        f.write(svg_content)
    
    # 生成 Markdown 报告
    generate_markdown_report(stats)
    
    print(f"✅ Done! Stats: {stats['stats']}")

def generate_mock_calendar_data(daily_breakdown):
    """从日统计生成模拟的 GitHub 日历数据"""
    weeks = []
    today = datetime.now()
    
    # 生成 52 周的数据
    start_date = today - timedelta(days=364)  # 从去年今天开始
    start_date = start_date - timedelta(days=start_date.weekday())  # 调整到周日
    
    for week in range(53):
        week_data = {"contributionDays": []}
        for day in range(7):
            date = start_date + timedelta(days=week * 7 + day)
            date_str = date.strftime("%Y-%m-%d")
            
            count = 0
            if date_str in daily_breakdown:
                count = daily_breakdown[date_str]["baobao"] + daily_breakdown[date_str]["sanbao"]
            
            # 确定颜色
            if count == 0:
                color = "#ebedf0"
            elif count <= 2:
                color = "#9be9a8"
            elif count <= 5:
                color = "#40c463"
            elif count <= 10:
                color = "#30a14e"
            else:
                color = "#216e39"
            
            week_data["contributionDays"].append({
                "date": date_str,
                "contributionCount": count,
                "color": color
            })
        weeks.append(week_data)
    
    return {"weeks": weeks}

def generate_markdown_report(stats):
    """生成 Markdown 报告"""
    report = f"""# 🐱 Mibao Family Contribution Stats

> Last updated: {datetime.now().strftime("%Y-%m-%d %H:%M UTC")}

## 📊 Overall Statistics

| Member | Commits | Percentage |
|--------|---------|------------|
| 👨‍💻 爸宝 (全全咪) | {stats['baobao_commits']} | {stats['stats']['baobao_percentage']}% |
| 🤖 三宝 (AI Agents) | {stats['sanbao_commits']} | {stats['stats']['sanbao_percentage']}% |
| **Total** | **{stats['total_commits']}** | **100%** |

## 🔥 Streak Stats

- **Current Streak**: {stats['stats']['current_streak']} days
- **Max Streak**: {stats['stats']['max_streak']} days

## 📈 Contribution Graph

![Mibao Family Contributions](./contributions.svg)

---

*Generated by Mibao Family Bot* 🐾
"""
    
    with open("stats/README.md", "w", encoding="utf-8") as f:
        f.write(report)

if __name__ == "__main__":
    main()
