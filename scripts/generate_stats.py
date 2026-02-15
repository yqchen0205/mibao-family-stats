#!/usr/bin/env python3
"""
Mibao Family Contribution Stats Generator
生成咪咪一家的 GitHub 贡献统计和可视化图表
使用 GitHub GraphQL API 直接获取数据
"""

import os
import json
import requests
from datetime import datetime, timedelta
from collections import defaultdict

def get_github_contributions(username, token=None):
    """使用 GitHub GraphQL API 获取用户的贡献数据"""
    query = """
    query($username: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $username) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          totalIssueContributions
          totalPullRequestContributions
          totalPullRequestReviewContributions
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
    
    # 获取过去一年的日期范围
    to_date = datetime.now()
    from_date = to_date - timedelta(days=365)
    
    variables = {
        "username": username,
        "from": from_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to": to_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    } if token else {}
    
    response = requests.post(
        "https://api.github.com/graphql",
        json={"query": query, "variables": variables},
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        return data.get("data", {}).get("user", {}).get("contributionsCollection", {})
    else:
        print(f"Error fetching data: {response.status_code}")
        print(response.text)
        return {}

def generate_contribution_heatmap(calendar_data, title="🐱 Mibao Family Contributions"):
    """生成 SVG 贡献热力图"""
    weeks = calendar_data.get("weeks", [])
    
    svg_width = 828
    svg_height = 140
    cell_size = 10
    cell_gap = 2
    
    svg_parts = [
        f'<svg width="{svg_width}" height="{svg_height}" xmlns="http://www.w3.org/2000/svg">',
        f'<text x="10" y="20" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif" font-size="14" font-weight="600" fill="#24292f">{title}</text>',
        '<g transform="translate(10, 35)">'
    ]
    
    # 添加月份标签
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    current_month = None
    for week_idx, week in enumerate(weeks):
        if week.get("contributionDays"):
            first_day = week["contributionDays"][0]
            date = datetime.strptime(first_day["date"], "%Y-%m-%d")
            month_abbr = months[date.month - 1]
            if month_abbr != current_month:
                x = week_idx * (cell_size + cell_gap)
                svg_parts.append(f'<text x="{x}" y="-6" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif" font-size="9" fill="#767676">{month_abbr}</text>')
                current_month = month_abbr
    
    # 添加星期标签
    weekdays = ["Mon", "Wed", "Fri"]
    for i, day in enumerate(weekdays):
        y = (i * 2 + 1) * (cell_size + cell_gap) + cell_size / 2
        svg_parts.append(f'<text x="-25" y="{y}" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif" font-size="9" fill="#767676">{day}</text>')
    
    # 添加贡献格子
    for week_idx, week in enumerate(weeks):
        for day_idx, day in enumerate(week.get("contributionDays", [])):
            count = day.get("contributionCount", 0)
            color = day.get("color", "#ebedf0")
            
            x = week_idx * (cell_size + cell_gap)
            y = day_idx * (cell_size + cell_gap)
            
            # 添加 tooltip 标题
            tooltip = f"{day['date']}: {count} contributions"
            
            svg_parts.append(
                f'<rect x="{x}" y="{y}" width="{cell_size}" height="{cell_size}" '
                f'fill="{color}" rx="2">'
                f'<title>{tooltip}</title>'
                f'</rect>'
            )
    
    # 添加图例
    legend_y = 85
    legend_x = 10
    legend_colors = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]
    legend_labels = ["No", "Low", "Medium", "High", "Very High"]
    
    svg_parts.append(f'<text x="{legend_x}" y="{legend_y + 10}" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif" font-size="10" fill="#767676">Less</text>')
    
    for i, (color, label) in enumerate(zip(legend_colors, legend_labels)):
        x = legend_x + 35 + i * 15
        svg_parts.append(f'<rect x="{x}" y="{legend_y}" width="{cell_size}" height="{cell_size}" fill="{color}" rx="2"/>')
    
    svg_parts.append(f'<text x="{legend_x + 115}" y="{legend_y + 10}" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif" font-size="10" fill="#767676">More</text>')
    
    svg_parts.extend([
        '</g>',
        '</svg>'
    ])
    
    return '\n'.join(svg_parts)

def calculate_streak(weeks):
    """计算当前连续贡献天数"""
    today = datetime.now()
    streak = 0
    
    # 收集所有有贡献的日期
    contribution_dates = set()
    for week in weeks:
        for day in week.get("contributionDays", []):
            if day.get("contributionCount", 0) > 0:
                contribution_dates.add(day["date"])
    
    # 计算连续天数
    for i in range(365):
        date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        if date in contribution_dates:
            streak += 1
        elif i > 0:  # 跳过今天
            break
    
    return streak

def calculate_max_streak(weeks):
    """计算最大连续贡献天数"""
    max_streak = 0
    current_streak = 0
    
    # 收集所有有贡献的日期
    contribution_dates = set()
    for week in weeks:
        for day in week.get("contributionDays", []):
            if day.get("contributionCount", 0) > 0:
                contribution_dates.add(day["date"])
    
    # 排序日期
    sorted_dates = sorted(contribution_dates)
    
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
    
    # GitHub 用户名
    BAOBAO_USERNAME = "yqchen0205"
    
    # 获取 GitHub Token
    token = os.environ.get("GITHUB_TOKEN")
    
    # 获取爸宝的贡献数据
    print(f"📊 Fetching {BAOBAO_USERNAME}'s contributions...")
    baobao_data = get_github_contributions(BAOBAO_USERNAME, token)
    
    if not baobao_data:
        print("❌ Failed to fetch contribution data")
        return
    
    # 提取数据
    calendar = baobao_data.get("contributionCalendar", {})
    total_contributions = calendar.get("totalContributions", 0)
    weeks = calendar.get("weeks", [])
    
    # 计算统计
    current_streak = calculate_streak(weeks)
    max_streak = calculate_max_streak(weeks)
    
    # 三宝的数据目前从本地统计，或者可以手动配置
    # 这里我们暂时用爸宝的数据作为基础，后续可以扩展
    
    stats = {
        "total_commits": total_contributions,
        "baobao_commits": total_contributions,  # 目前全部算爸宝的
        "sanbao_commits": 0,  # 暂时设为 0，后续可以从特定仓库统计
        "stats": {
            "baobao_percentage": 100.0 if total_contributions > 0 else 0,
            "sanbao_percentage": 0.0,
            "current_streak": current_streak,
            "max_streak": max_streak
        },
        "calendar": calendar,
        "fetched_at": datetime.now().isoformat()
    }
    
    # 保存 JSON 数据
    os.makedirs("stats", exist_ok=True)
    with open("stats/contributions.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    # 生成 SVG 图表
    svg_content = generate_contribution_heatmap(calendar, "🐱 Mibao Family Contributions")
    with open("stats/contributions.svg", "w", encoding="utf-8") as f:
        f.write(svg_content)
    
    # 生成 Markdown 报告
    generate_markdown_report(stats)
    
    print(f"✅ Done!")
    print(f"   Total contributions: {total_contributions}")
    print(f"   Current streak: {current_streak} days")
    print(f"   Max streak: {max_streak} days")

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
