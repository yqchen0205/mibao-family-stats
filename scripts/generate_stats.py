#!/usr/bin/env python3
"""
Mibao Family Contribution Stats Generator - Full Commit Mode
全面统计指定邮箱的所有 commit（绕过 GitHub 原生 contribution 规则）
"""

import os
import json
import requests
from datetime import datetime, timedelta
from collections import defaultdict

def get_all_repos(token, username="yqchen0205"):
    """获取用户可访问的所有仓库（包括 private）"""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    repos = []
    page = 1
    
    while True:
        # 获取用户有权限的仓库（包括 collaborator）
        url = f"https://api.github.com/user/repos"
        params = {
            "per_page": 100,
            "page": page,
            "affiliation": "owner,collaborator,organization_member",
            "sort": "updated",
            "direction": "desc"
        }
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            print(f"   ✗ Error fetching repos: {response.status_code}")
            break
        
        data = response.json()
        if not data:
            break
        
        repos.extend(data)
        
        if len(data) < 100:
            break
        
        page += 1
        if page > 10:
            break
    
    return repos

def get_repo_commits(owner, repo, author_email, since, token):
    """获取仓库中指定作者的 commits"""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    commits = []
    page = 1
    
    while True:
        url = f"https://api.github.com/repos/{owner}/{repo}/commits"
        params = {
            "author": author_email,
            "since": since,
            "per_page": 100,
            "page": page
        }
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            if response.status_code == 409:  # Empty repo or other issue
                break
            print(f"   ✗ Error fetching {owner}/{repo}: {response.status_code}")
            break
        
        data = response.json()
        if not data or not isinstance(data, list):
            break
        
        commits.extend(data)
        
        if len(data) < 100:
            break
        
        page += 1
        if page > 10:
            break
    
    return commits

def generate_contribution_heatmap(contributions_by_date, title="🐱 Mibao Family Contributions"):
    """生成 SVG 贡献热力图"""
    
    # 生成过去一年的日历数据
    weeks = []
    today = datetime.now()
    start_date = today - timedelta(days=364)
    start_date = start_date - timedelta(days=start_date.weekday())
    
    for week_idx in range(53):
        week_data = {"contributionDays": []}
        for day_idx in range(7):
            date = start_date + timedelta(days=week_idx * 7 + day_idx)
            date_str = date.strftime("%Y-%m-%d")
            
            count = contributions_by_date.get(date_str, 0)
            
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
            
            tooltip = f"{day['date']}: {count} commits"
            
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
    
    svg_parts.append(f'<text x="{legend_x}" y="{legend_y + 10}" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif" font-size="10" fill="#767676">Less</text>')
    
    for i, color in enumerate(legend_colors):
        x = legend_x + 35 + i * 15
        svg_parts.append(f'<rect x="{x}" y="{legend_y}" width="{cell_size}" height="{cell_size}" fill="{color}" rx="2"/>')
    
    svg_parts.append(f'<text x="{legend_x + 115}" y="{legend_y + 10}" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif" font-size="10" fill="#767676">More</text>')
    
    svg_parts.extend([
        '</g>',
        '</svg>'
    ])
    
    return '\n'.join(svg_parts)

def calculate_streak(contributions_by_date):
    """计算当前连续贡献天数"""
    today = datetime.now()
    streak = 0
    
    for i in range(365):
        date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        if contributions_by_date.get(date, 0) > 0:
            streak += 1
        elif i > 0:
            break
    
    return streak

def calculate_max_streak(contributions_by_date):
    """计算最大连续贡献天数"""
    max_streak = 0
    current_streak = 0
    
    sorted_dates = sorted(contributions_by_date.keys())
    
    prev_date = None
    for date_str in sorted_dates:
        if contributions_by_date[date_str] > 0:
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
    print("🐱 Generating Mibao Family Contribution Stats (Full Commit Mode)...")
    
    # 配置
    AUTHOR_EMAIL = "Mibao0211@163.com"  # 要统计的邮箱
    
    # 获取 GitHub Token
    token = os.environ.get("GITHUB_TOKEN")
    
    if not token:
        print("❌ No GITHUB_TOKEN found!")
        return
    
    print(f"🔑 Token found (length: {len(token)})")
    
    # 获取过去一年的日期
    since = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # 获取所有可访问的仓库
    print("📊 Discovering accessible repositories...")
    repos = get_all_repos(token)
    print(f"   Found {len(repos)} repositories")
    
    # 统计每个仓库的 commit
    contributions_by_date = defaultdict(int)
    total_commits = 0
    repos_with_commits = 0
    
    for repo in repos:
        owner = repo.get("owner", {}).get("login", "")
        repo_name = repo.get("name", "")
        full_name = f"{owner}/{repo_name}"
        is_private = repo.get("private", False)
        
        if not owner or not repo_name:
            continue
        
        privacy_tag = "(private)" if is_private else "(public)"
        print(f"   🔍 Checking {full_name} {privacy_tag}...", end=" ")
        
        commits = get_repo_commits(owner, repo_name, AUTHOR_EMAIL, since, token)
        
        if commits:
            repos_with_commits += 1
            print(f"✓ {len(commits)} commits")
            
            for commit in commits:
                commit_date = commit.get("commit", {}).get("author", {}).get("date", "")[:10]
                if commit_date:
                    contributions_by_date[commit_date] += 1
                    total_commits += 1
        else:
            print("0")
    
    print(f"\n📊 Summary:")
    print(f"   • Repositories scanned: {len(repos)}")
    print(f"   • Repositories with commits: {repos_with_commits}")
    print(f"   • Total commits: {total_commits}")
    
    # 计算统计
    current_streak = calculate_streak(contributions_by_date)
    max_streak = calculate_max_streak(contributions_by_date)
    
    print(f"   • Current streak: {current_streak} days")
    print(f"   • Max streak: {max_streak} days")
    
    stats = {
        "total_commits": total_commits,
        "repos_scanned": len(repos),
        "repos_with_commits": repos_with_commits,
        "current_streak": current_streak,
        "max_streak": max_streak,
        "contributions_by_date": dict(contributions_by_date),
        "fetched_at": datetime.now().isoformat()
    }
    
    # 保存 JSON 数据
    os.makedirs("stats", exist_ok=True)
    with open("stats/contributions.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    # 生成 SVG 图表
    svg_content = generate_contribution_heatmap(contributions_by_date, "🐱 Mibao Family Contributions")
    with open("stats/contributions.svg", "w", encoding="utf-8") as f:
        f.write(svg_content)
    
    # 生成 Markdown 报告
    generate_markdown_report(stats)
    
    print(f"\n✅ Done! Total: {total_commits} commits")

def generate_markdown_report(stats):
    """生成 Markdown 报告"""
    report = f"""# 🐱 Mibao Family Contributions

> Last updated: {datetime.now().strftime("%Y-%m-%d %H:%M UTC")}
> Mode: Full Commit Scan (bypass GitHub native contribution rules)

**{stats['total_commits']} commits in the last year**

- Repositories scanned: {stats['repos_scanned']}
- Repositories with commits: {stats['repos_with_commits']}

## 📈 Contribution Graph

![Contributions](./contributions.svg)

## 🔥 Streak Stats

- **Current Streak**: {stats['current_streak']} days
- **Max Streak**: {stats['max_streak']} days

---

*Generated by Mibao Bot* 🐾
"""
    
    with open("stats/README.md", "w", encoding="utf-8") as f:
        f.write(report)

if __name__ == "__main__":
    main()
