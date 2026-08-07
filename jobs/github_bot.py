import urllib.request
import json
import os

class GitHubBot:
    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN")

    def post_comment(self, issue_url: str, comment_text: str):
        if not self.token or self.token.startswith("ghp_aapka"):
            print("⚠️ [GitHub Bot] Valid GITHUB_TOKEN missing in .env. Skipping live comment.")
            return False

        # issue_url example: https://github.com/owner/repo/issues/123
        parts = issue_url.rstrip('/').split('/')
        if len(parts) >= 7 and parts[2] == "github.com":
            owner = parts[3]
            repo = parts[4]
            issue_number = parts[6]
            api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/comments"
        else:
            api_url = issue_url.replace("github.com", "api.github.com/repos") + "/comments"

        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AI-Freelancer-Agent"
        }

        payload = json.dumps({"body": f"🤖 **AI Agent Proposed Solution:**\n\n```python\n{comment_text}\n```\n\n*Generated automatically by Autonomous AI Freelancer Network.*"}).encode('utf-8')

        try:
            req = urllib.request.Request(api_url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req) as response:
                if response.status == 201:
                    print(f"✅ [GitHub Bot] Successfully posted solution comment to issue!")
                    return True
        except Exception as e:
            print(f"❌ [GitHub Bot Failed] Could not post comment: {e}")
            return False