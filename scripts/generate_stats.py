#!/usr/bin/env python3
"""
Mibao Family Contribution Stats Generator
全面统计 GitHub 账号的贡献（支持手动添加特定仓库的 commit）
"""

import os
import json
import requests
from datetime import datetime, timedelta
from collections import defaultdict

def get_contributions_collection(username, token=None):
    """使用 GitHub GraphQL API 获取官方贡献统计"""
    query = """
    query($username: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $username) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          totalIssueContributions
          totalPullRequestContributions
          totalPullRequestReviewContributions
          totalRepositoryContributions
          restrictedContributionsCount
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
        print(f"Error: {response.status_code}")
        print(response.text)
        return {}

def get_repo_commits(owner, repo, author_email, since, token=None):
    """使用 GitHub REST API 获取特定仓库中指定作者的 commit"""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    } if token else {"Accept": "application/vnd.github.v3+json"}
    
    commits = []
    page = 1
    
    while True:
        url = f"https://api.github.com/repos/{owner}/{repo}/commits"
        params = {
            "author": author_email,  # 使用邮箱过滤
            "since": since,
            "per_page": 100,
            "page": page
        }
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            print(f"   ✗ Error fetching {owner}/{repo}: {response.status_code}")
            break
        
        data = response.json()
        if not data:
            break
        
        commits.extend(data)
        
        if len(data) < 100:
            break
        
        page += 1
        if page > 10:  # 限制最多 1000 条
            break
    
    return commits

def get_all_contributions(username, token=None):
    """综合获取用户贡献数据"""
    contributions_by_date = defaultdict(int)
    
    # 1. 从 contributionsCollection 获取基础数据
    print("📊 Fetching from contributionsCollection...")
    collection = get_contributions_collection(username, token)
    
    calendar = collection.get("contributionCalendar", {})
    official_total = calendar.get("totalContributions", 0)
    
    print(f"   ✓ Official count: {official_total} contributions")
    print(f"   ✓ Restricted (private): {collection.get('restrictedContributionsCount', 0)}")
    
    # 提取官方日历数据
    for week in calendar.get("weeks", []):
        for day in week.get("contributionDays", []):
            date = day["date"]
            count = day["contributionCount"]
            contributions_by_date[date] = count
    
    # 2. 手动统计特定仓库的 commit（补充那些未被 GitHub 统计的）
    # 配置需要额外统计的仓库
    extra_repos = [
        # (owner, repo, author_email)
        # 例如：("yqchen0205", "my-private-repo", "Mibao0211@163.com")
    ]
    
    # 手动扫描特定仓库
    # 配置需要扫描的仓库列表 (owner, repo, author_email)
    repos_to_scan = [
        # 可以在这里添加更多仓库
    ]
    
    # 尝试自动发现 yqchen0205 的仓库（因为 Mibao0211 的 commit 可能在爸宝的仓库里）
    print("📊 Discovering yqchen0205's repositories...")
    
    discover_query = """
    query($username: String!) {
      user(login: $username) {
        repositories(first: 100, privacy: PRIVATE, ownerAffiliations: OWNER) {
          nodes {
            nameWithOwner
            isPrivate
          }
        }
      }
    }
    """
    
    discover_response = requests.post(
        "https://api.github.com/graphql",
        json={"query": discover_query, "variables": {"username": "yqchen0205"}},
        headers=headers
    )
    
    if discover_response.status_code == 200:
        discover_data = discover_response.json()
        yq_repos = discover_data.get("data", {}).get("user", {}).get("repositories", {}).get("nodes", [])
        print(f"   Found {len(yq_repos)} repositories from yqchen0205")
        
        for repo in yq_repos:
            name_with_owner = repo.get("nameWithOwner", "")
            if name_with_owner:
                repos_to_scan.append((name_with_owner.split("/")[0], name_with_owner.split("/")[1], "Mibao0211@163.com"))
    
    # 扫描配置的仓库
    print("📊 Scanning configured repositories...")
    manual_count = 0
    
    for owner, repo_name, author_email in repos_to_scan:
        print(f"   🔍 Checking {owner}/{repo_name} for {author_email}...")
        
        commits = get_repo_commits(owner, repo_name, author_email, since, token)
        
        for commit in commits:
            commit_date = commit.get("commit", {}).get("author", {}).get("date", "")[:10]
            if commit_date:
                contributions_by_date[commit_date] += 1
                manual_count += 1
        
        if commits:
            print(f"   ✓ Found {len(commits)} commits")
    
    total = sum(contributions_by_date.values())
    print(f"📊 Total after manual scan: {total} contributions")
    print(f"   (Added {manual_count} from manual scan)")
    
    return {
        "contributions_by_date": dict(contributions_by_date),
        "calendar": calendar,
        "total_contributions": total,
        "official_count": official_total,
        "manual_count": manual_count
    }

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
    print("🐱 Generating Mibao Family Contribution Stats...")
    
    # GitHub 用户名 - 咪咪一家的账号
    MIBAO_USERNAME = "Mibao0211"
    
    # 获取 GitHub Token
    token = os.environ.get("GITHUB_TOKEN")
    
    # 调试信息
    if token:
        print(f"🔑 Token found (length: {len(token)})")
        if token.startswith("ghs_"):
            print("⚠️  Using default GITHUB_TOKEN")
        else:
            print("✅ Using custom PAT token")
    else:
        print("❌ No token found!")
    
    # 获取贡献数据
    print(f"📊 Fetching {MIBAO_USERNAME}'s contributions...")
    result = get_all_contributions(MIBAO_USERNAME, token)
    
    if not result:
        print("❌ Failed to fetch contribution data")
        return
    
    contributions_by_date = result["contributions_by_date"]
    total_contributions = result["total_contributions"]
    
    print(f"\n📊 Summary:")
    print(f"   • Official GitHub count: {result['official_count']}")
    print(f"   • Manual scan added: {result['manual_count']}")
    print(f"   • Total: {total_contributions} contributions")
    
    # 计算统计
    current_streak = calculate_streak(contributions_by_date)
    max_streak = calculate_max_streak(contributions_by_date)
    
    print(f"🔥 Current streak: {current_streak} days")
    print(f"🏆 Max streak: {max_streak} days")
    
    stats = {
        "total_commits": total_contributions,
        "official_count": result["official_count"],
        "manual_count": result["manual_count"],
        "current_streak": current_streak,
        "max_streak": max_streak,
        "contributions_by_date": contributions_by_date,
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
    
    print(f"\n✅ Done! Total: {total_contributions} contributions")

def generate_markdown_report(stats):
    """生成 Markdown 报告"""
    report = f"""# 🐱 Mibao Family Contributions

> Last updated: {datetime.now().strftime("%Y-%m-%d %H:%M UTC")}

**{stats['total_commits']} contributions in the last year**

- Official GitHub count: {stats['official_count']}
- Additional from manual scan: {stats['manual_count']}

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
