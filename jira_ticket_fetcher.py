#!/usr/bin/env python3
"""
Jira Ticket Fetcher - Fetches ticket descriptions and acceptance criteria using JQL
"""

import os
import requests
import json
from base64 import b64encode
from typing import List, Dict, Any
import anthropic

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Warning: python-dotenv not installed. Install with: pip install python-dotenv")
    print("Falling back to system environment variables...")

class JiraTicketFetcher:
    def __init__(self, jira_url: str, email: str, api_token: str):
        self.jira_url = jira_url.rstrip('/')
        self.email = email
        self.api_token = api_token
        self.auth_header = self._create_auth_header()
        
    def _create_auth_header(self) -> str:
        """Create basic auth header for Jira API"""
        credentials = f"{self.email}:{self.api_token}"
        encoded_credentials = b64encode(credentials.encode()).decode()
        return f"Basic {encoded_credentials}"
    
    def search_tickets(self, jql: str, fields: List[str] = None) -> Dict[str, Any]:
        """Search for tickets using JQL query"""
        if fields is None:
            fields = ["summary", "description", "key", "status", "assignee"]
        
        url = f"{self.jira_url}/rest/api/3/search"
        headers = {
            "Authorization": self.auth_header,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        payload = {
            "jql": jql,
            "fields": fields,
            "maxResults": 100  # Adjust as needed
        }
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error: {response.status_code} - {response.text}")
            return {}
    
    def get_field_info(self) -> Dict[str, Any]:
        """Get all available fields to find custom field IDs"""
        url = f"{self.jira_url}/rest/api/3/field"
        headers = {
            "Authorization": self.auth_header,
            "Accept": "application/json"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching fields: {response.status_code} - {response.text}")
            return []
    
    def find_acceptance_criteria_field(self) -> str:
        """Find the field ID for Acceptance Criteria"""
        # Use environment variable if set, otherwise search
        ac_field_id = os.getenv('ACCEPTANCE_CRITERIA_FIELD')
        if ac_field_id:
            print(f"Using specified Acceptance Criteria field: {ac_field_id}")
            return ac_field_id
        
        fields = self.get_field_info()
        
        # Common names for acceptance criteria fields
        ac_field_names = [
            "acceptance criteria",
            "acceptancecriteria", 
            "acceptance_criteria",
            "ac",
            "criteria",
            "definition of done",
            "dod"
        ]
        
        print("\nSearching for Acceptance Criteria field...")
        found_field = None
        
        for field in fields:
            field_name = field.get('name', '').lower()
            if any(ac_name in field_name for ac_name in ac_field_names):
                print(f"Found potential AC field: {field['name']} (ID: {field['id']})")
                found_field = field['id']
                break
        
        if not found_field:
            print("No exact Acceptance Criteria field found. Available custom fields:")
            custom_fields = [f for f in fields if f['id'].startswith('customfield_')]
            for field in custom_fields[:15]:  # Show first 15 custom fields
                print(f"  - {field['name']} (ID: {field['id']})")
            
            # Let user choose a field if running interactively
            try:
                field_choice = input("\nEnter field ID to use for Acceptance Criteria (or press Enter to skip): ").strip()
                if field_choice:
                    found_field = field_choice
            except EOFError:
                pass
        
        return found_field
    
    def find_development_field(self) -> str:
        """Find the field ID for Development section"""
        fields = self.get_field_info()
        
        print("\nSearching for Development field...")
        print("Looking for fields that might contain development/PR data...")
        
        # Look for development-related fields
        dev_candidates = []
        
        for field in fields:
            field_name = field.get('name', '').lower()
            field_id = field.get('id', '')
            field_type = field.get('schema', {}).get('type', 'unknown')
            
            # Check for development-related names
            if any(keyword in field_name for keyword in ['development', 'dev', 'pull', 'pr', 'github', 'git', 'branch', 'commit']):
                dev_candidates.append({
                    'name': field['name'],
                    'id': field_id,
                    'type': field_type
                })
                print(f"📋 Found: {field['name']} (ID: {field_id}, Type: {field_type})")
        
        # Also check for any fields that might be hidden/system fields
        system_candidates = []
        for field in fields:
            field_name = field.get('name', '')
            field_id = field.get('id', '')
            field_type = field.get('schema', {}).get('type', 'unknown')
            
            # Look for system fields that might contain development data
            if (not field_name or 
                field_type in ['any', 'option', 'array'] or 
                field_id.startswith('customfield_') and 'dev' in field_name.lower()):
                system_candidates.append({
                    'name': field_name or 'Unknown',
                    'id': field_id,
                    'type': field_type
                })
        
        print(f"\n🔍 Found {len(dev_candidates)} development-related fields")
        print(f"🔍 Found {len(system_candidates)} potential system fields")
        
        if dev_candidates:
            return dev_candidates[0]['id']
        
        # If no direct matches, let's try to fetch the issue and see what fields actually contain data
        print("\n🔎 No obvious development fields found, checking issue data...")
        return self._find_development_field_by_content()
    
    def _find_development_field_by_content(self) -> str:
        """Try to find development field by examining issue content"""
        # Get the issue with all fields
        issue_url = f"{self.jira_url}/rest/api/3/issue/PDW-9468"
        headers = {
            "Authorization": self.auth_header,
            "Accept": "application/json"
        }
        
        response = requests.get(issue_url, headers=headers)
        if response.status_code == 200:
            issue_data = response.json()
            fields = issue_data.get('fields', {})
            
            print("🔍 Examining all fields in the issue for development-related content...")
            
            for field_id, field_value in fields.items():
                if field_value is not None:
                    field_str = str(field_value).lower()
                    
                    # Look for GitHub URLs, PR references, or development keywords
                    if any(keyword in field_str for keyword in [
                        'github.com', 'pull', 'pr', 'branch', 'commit', 
                        'dbus/pull', 'ConsumerAffairs/dbus'
                    ]):
                        print(f"🎯 Found potential development content in field {field_id}")
                        print(f"   Content preview: {str(field_value)[:200]}...")
                        return field_id
            
            print("❌ No fields found containing obvious development content")
        
        return None
    
    def _extract_text_content(self, field_content) -> str:
        """Extract plain text from various Jira field formats"""
        if not field_content:
            return "No content provided"
        
        # Handle string content
        if isinstance(field_content, str):
            return field_content
        
        # Handle Atlassian Document Format (ADF)
        if isinstance(field_content, dict):
            if 'content' in field_content:
                return self._extract_adf_text(field_content)
            else:
                return str(field_content)
        
        # Handle other types
        return str(field_content)
    
    def _extract_adf_text(self, adf_content) -> str:
        """Extract text from Atlassian Document Format"""
        text_parts = []
        
        def extract_text_recursive(node):
            if isinstance(node, dict):
                # Extract text from text nodes
                if node.get('type') == 'text':
                    text_parts.append(node.get('text', ''))
                
                # Process content array
                if 'content' in node:
                    for child in node['content']:
                        extract_text_recursive(child)
                        
                # Add line breaks for paragraphs
                if node.get('type') == 'paragraph':
                    text_parts.append('\n')
            
            elif isinstance(node, list):
                for item in node:
                    extract_text_recursive(item)
        
        extract_text_recursive(adf_content)
        
        # Join and clean up the text
        text = ''.join(text_parts).strip()
        # Remove excessive newlines
        text = '\n'.join(line.strip() for line in text.split('\n') if line.strip())
        
        return text if text else "No content provided"
    
    def fetch_tickets_with_criteria(self, jql: str) -> List[Dict[str, Any]]:
        """Fetch tickets with description and acceptance criteria"""
        # Find acceptance criteria field
        ac_field_id = self.find_acceptance_criteria_field()
        
        # Define fields to fetch
        fields = ["key", "summary", "description", "status", "assignee", "created", "updated"]
        
        # Add custom description field if specified
        description_field_id = os.getenv('DESCRIPTION_FIELD')
        if description_field_id and description_field_id not in fields:
            fields.append(description_field_id)
        
        # Add acceptance criteria field
        if ac_field_id and ac_field_id not in fields:
            fields.append(ac_field_id)
        
        # Add all custom fields to see what's available (for debugging)
        all_fields = self.get_field_info()
        custom_fields = [f['id'] for f in all_fields if f['id'].startswith('customfield_')]
        fields.extend(custom_fields[:10])  # Add first 10 custom fields for inspection
        
        # Search for tickets
        results = self.search_tickets(jql, fields)
        
        if not results:
            return []
        
        tickets = []
        for issue in results.get('issues', []):
            # Extract description from custom field if specified, otherwise use standard description
            description_field_id = os.getenv('DESCRIPTION_FIELD', 'description')
            description_field = issue['fields'].get(description_field_id)
            description = self._extract_text_content(description_field)
            
            # Get acceptance criteria if field exists
            acceptance_criteria = None
            if ac_field_id and ac_field_id in issue['fields']:
                ac_content = issue['fields'][ac_field_id]
                acceptance_criteria = self._extract_text_content(ac_content)
            
            ticket_data = {
                'key': issue['key'],
                'summary': issue['fields'].get('summary', 'No summary'),
                'description': description,
                'status': issue['fields'].get('status', {}).get('name', 'Unknown'),
                'acceptance_criteria': acceptance_criteria,
                'assignee': issue['fields']['assignee']['displayName'] if issue['fields'].get('assignee') else None,
                'created': issue['fields'].get('created', ''),
                'updated': issue['fields'].get('updated', '')
            }
            
            # Fetch PR information using GitHub API search
            pr_info = self.fetch_prs_from_github(issue['key'])
            if pr_info:
                ticket_data['pull_requests'] = pr_info
            
            tickets.append(ticket_data)
        
        return tickets
    
    def print_tickets(self, tickets: List[Dict[str, Any]]):
        """Print tickets in a readable format"""
        print(f"✅ Tickets found: {len(tickets)}")
        
        for ticket in tickets:
            print(f"\n📋 Issue: {ticket['key']}")
            print(f"📝 Summary: {ticket['summary']}")
            print(f"📄 Description:")
            
            description = ticket['description'] or 'No description provided'
            # Format the description with proper markdown styling
            formatted_description = self._format_description(description)
            print(formatted_description)
            
            # Display PR information if available
            if 'pull_requests' in ticket and ticket['pull_requests']:
                prs = ticket['pull_requests']
                print(f"\n📋 Pull Requests ({len(prs)}):")
                for repo, pr in prs.items():
                    print(f"  Repository: {repo}")
                    print(f"  - PR #{pr.get('number')}: {pr.get('title')}")
                    print(f"    State: {pr.get('state')} | Author: {pr.get('author')}")
                    print(f"    URL: {pr.get('url')}")
                    if pr.get('body'):
                        body_preview = pr['body'][:100] + '...' if len(pr['body']) > 100 else pr['body']
                        print(f"    Description: {body_preview}")
                    
                    # Display code changes summary if available
                    if pr.get('code_changes'):
                        changes = pr['code_changes']
                        print(f"    📁 Code Changes: {changes['total_files']} files")
                        print(f"       +{changes['summary']['additions']} -{changes['summary']['deletions']} lines")
                        
                        # Show top 3 files changed
                        files = changes.get('files', [])[:3]
                        for file_info in files:
                            print(f"       • {file_info['filename']} ({file_info['status']}) +{file_info['additions']} -{file_info['deletions']}")
                        
                        if len(changes.get('files', [])) > 3:
                            print(f"       ... and {len(changes['files']) - 3} more files")
                    
                    print()
            else:
                print(f"\n🔗 Pull Requests: No PRs found")
            
            print("=" * 60)
            if ticket['acceptance_criteria']:
                print("✅ Acceptance Criteria:")
                ac_formatted = self._format_acceptance_criteria(ticket['acceptance_criteria'])
                print(ac_formatted)
            else:
                print("✅ Acceptance Criteria: Not found or not set")
    
    def _format_description(self, description: str) -> str:
        """Format description with proper markdown styling"""
        if description == 'No description provided':
            return description
        
        # Replace section headers with markdown formatting
        formatted = description.replace('WHAT:', '**WHAT:**')
        formatted = formatted.replace('WHY:', '\n**WHY:**')
        formatted = formatted.replace('Story/Task details', '\n### Story/Task details')
        formatted = formatted.replace('Business', '**Business**')
        formatted = formatted.replace('QA', '\n**QA**')
        formatted = formatted.replace('Admin', '\n**Admin**')
        formatted = formatted.replace('Code Summary', '\n**Code Summary**')
        formatted = formatted.replace('Additional Context', '\n**Additional Context**')
        
        # Add bullet points for lists
        lines = formatted.split('\n')
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if line.startswith('Creating a new') or line.startswith('Registering it') or line.startswith('Refactoring the base') or line.startswith('A partial refactor') or line.startswith('This task focuses') or line.startswith('This addresses'):
                line = f"• {line}"
            formatted_lines.append(line)
        
        return '\n'.join(formatted_lines)
    
    def _format_acceptance_criteria(self, criteria: str) -> str:
        """Format acceptance criteria with bullet points"""
        if not criteria:
            return "Not found or not set"
        
        # Split by lines and add bullet points
        lines = criteria.split('\n')
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('•') and not line.startswith('-'):
                line = f"• {line}"
            formatted_lines.append(line)
        
        return '\n'.join(formatted_lines)
    
    def generate_test_cases(self, ticket_data: Dict[str, Any], pr_context: str = "") -> tuple[str | None, str]:
        """Generate test cases using Claude AI based on ticket data"""
        issue_key = ticket_data.get('key', 'Unknown')
        summary = ticket_data.get('summary', 'No summary')
        description = ticket_data.get('description', 'No description')
        acceptance_criteria = ticket_data.get('acceptance_criteria', 'No acceptance criteria')
        
        print(f"🤖 Using Claude AI to generate test cases based on comprehensive context...")
        
        # Create comprehensive context for test case generation
        context = f"""TICKET: {issue_key}
SUMMARY: {summary}

DESCRIPTION:
{description}

ACCEPTANCE CRITERIA:
{acceptance_criteria}"""
        
        if pr_context:
            context += pr_context
            print(f"📋 Including enhanced context ({len(pr_context)} characters)")
        
        # Store the context that will be used for test case generation
        generation_context = context
        
        # Generate test cases using Claude AI with all the context
        prompt = f"""You are a QA expert generating comprehensive test cases for a software development ticket to be executed in our QA environment.
think" < "think hard" < "think harder" < "ultrathink.
Based on the following context, generate detailed, specific test cases that cover:
1. Implementation verification based on actual code changes
2. Acceptance criteria validation  
3. Developer-provided test guidance from PR descriptions
4. Regression testing for existing functionality
5. Edge cases and error scenarios
6. Integration testing

Context:
{context}

Generate test cases in this format:

### Test Case 1 – Verify Task Deletes Sessions Older Than 30 Days (dtc)

**Steps:**

1. Connect to the **dtc** application environment.
2. Open Django shell:

   ```bash
   python manage.py shell
   ```
3. Insert test records into `django_session`:

   * Some sessions with `expire_date` > 30 days ago.
   * Some sessions within the last 30 days.
4. Import and run cleanup task:

   ```python
   from app.common.tasks import cleanup_django_sessions
   cleanup_django_sessions()
   ```
5. Query `django_session` table after execution:

   ```sql
   SELECT COUNT(*) FROM django_session;
   ```

**Expected:**

* Sessions older than 30 days are **deleted**.
* Recent sessions remain intact.

---

### Test Case 2 – Verify Task Logs Properly When No Sessions To Delete (dtc)

**Steps:**

1. Ensure all sessions in **dtc** are recent (within 30 days).
2. Run the cleanup task manually (same steps as above).
3. Check logs or console output.

**Expected:**

* Log states **“No expired sessions found”**.
* Task exits without error.

---

### Test Case 3 – Verify Task Scheduled in Celery Beat (dtc)

**Steps:**

1. Open Django Admin for **dtc**:

   ```
   https://mainsite-01.qa.consumeraffairs.com/admin/django_celery_beat/periodictask/
   ```
2. Find task named:
   **`cleanup_django_sessions`** or similar.
3. Validate:

   * Enabled.
   * Cron schedule: `0 0 * * *` (**runs daily at 12:00 AM**).
   * Timezone: `US/Central`.

**Expected:**

* Task is scheduled correctly for daily execution.






QA Environment Requirements:
- All test cases will be performed in our QA environment
- Use Django admin interface to check data if possible
- Use Django shell if indicated in the PR description or code changes
- Access APIs through proper authentication and endpoints
- We don't have to run the migrations in the QA environment, it will be automatically done by the application

QA Environment Base URLs (use these in test cases):
- STYLEGUIDE_URL = "https://qa-styleguide.consumeraffairs.com"
- MAINSITE_URL = "https://mainsite-01.qa.consumeraffairs.com"
- SB_URL = "https://my-01.qa.consumeraffairs.com"
- LEADS_API_BASE_URL = "https://leads-api-01.qa.consumeraffairs.com"
- TOOLS_URL = "https://qa-tools.consumeraffairs.com"
- COMMHUB_URL = "http://qa-commhub.consumeraffairs.com"
- DBUS_URL = "https://dbus-01.qa.consumeraffairs.com"
- DTC_BASE_URL = "https://qa-dtc.consumeraffairs.com"
- AUTH_URL = "https://accounts-01.qa.consumeraffairs.com"
- REVIEWS_API_BASE_URL = "https://reviews-api-01.qa.consumeraffairs.com"
- MATCH_API_BASE_URL = "https://match-api-01.qa.consumeraffairs.com"
- USERDB_ENDPOINT_URL = "https://userdb-01.qa.consumeraffairs.com"
- BRANDS_APP_FRONTEND_URL = "https://qa-aspect.consumeraffairs.com"
- BRANDS_API_BASE_URL = "https://brands-api-01.qa.consumeraffairs.com"

Repository to Application Mapping:
- leads-api → LEADS_API_BASE_URL (https://leads-api-01.qa.consumeraffairs.com)
- dbus → DBUS_URL (https://dbus-01.qa.consumeraffairs.com)  
- ConsumerAffairs → MAINSITE_URL (https://mainsite-01.qa.consumeraffairs.com/) [Mainsite]
- silverback → SB_URL (https://my-01.qa.consumeraffairs.com) [Silverback]
- dtc → DTC_BASE_URL (https://qa-dtc.consumeraffairs.com)
- reviews-api → REVIEWS_API_BASE_URL (https://reviews-api-01.qa.consumeraffairs.com)
- match-api → MATCH_API_BASE_URL (https://match-api-01.qa.consumeraffairs.com)
- brandsapp-redesign → BRANDS_API_BASE_URL (https://brands-api-01.qa.consumeraffairs.com) [Backend]
- brandsapp-redesign-nextjs → BRANDS_APP_FRONTEND_URL (https://qa-aspect.consumeraffairs.com/) [Frontend]
- userdb → USERDB_ENDPOINT_URL (https://userdb-01.qa.consumeraffairs.com)
- commhub → COMMHUB_URL (http://qa-commhub.consumeraffairs.com)
- tools → TOOLS_URL (https://qa-tools.consumeraffairs.com)
- auth → AUTH_URL (https://accounts-01.qa.consumeraffairs.com)

Requirements:
- ALWAYS incorporate developer testing guidance from PR descriptions (look for any sections containing "Test")
- Try to group test cases into test steps when possible and very related to each other
- Convert developer-provided test steps into actionable QA test cases with exact commands
- Include specific shell commands, imports, or code snippets that developers specified
- AUTOMATICALLY identify the correct QA environment URL based on the repository name from PR context using the mapping above
- Provide CLEAR, EXECUTABLE steps with:
  * Exact URLs to navigate to using the QA base URLs provided above based on repository mapping
  * For UI testing: Use frontend URLs (e.g., "Navigate to https://qa-aspect.consumeraffairs.com/" for brandsapp-redesign-nextjs)
  * For API testing: Use API endpoints (e.g., "POST to https://leads-api-01.qa.consumeraffairs.com/api/v1/validate" for leads-api)
  * For Django admin: Use admin interfaces (e.g., "Navigate to https://mainsite-01.qa.consumeraffairs.com/admin/" for ConsumerAffairs repo)
  * Specific buttons/links to click (e.g., "Click the 'Submit' button")
  * Exact commands to run in Django shell (e.g., "from app.common.tasks import cleanup_django_sessions")
  * Where to look for results (e.g., "Check application logs", "Verify in Django admin interface")
  * Use the appropriate QA base URL for ALL types of testing (UI, API, admin) based on the repository identified from the PR context
  * Keep FrontEnd and Backend Test Cases separate
- Be specific to the actual implementation details provided in the code changes
- Include both positive and negative test scenarios  
- Reference specific class names, methods, or components from the code changes
- Make every step actionable for QA environment constraints
- Specify expected log messages, Django admin changes, or UI feedback
- If testing APIs, include exact endpoints, headers, and payload examples suitable for QA environment
- Try to build the test cases like a QA engineer would do
- Try to make them easy to understand for Product Owners

IMPORTANT: Generate ONLY the test cases without any introductory text or concluding summary. Start directly with the first test case heading and end with the last test case. Do not include phrases like "Based on the provided context" at the beginning or "These test cases cover..." at the end.

Generate comprehensive, QA environment-appropriate test cases now:"""

        # Call external AI generation script with the context
        print(f"🔄 Generating test cases with Claude AI...")
        print(f"📝 Context length: {len(context)} characters")
        
        try:
            # Initialize Claude client
            client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
            
            # Generate test cases using Claude
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4000,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            test_cases = response.content[0].text
            print(f"✅ Successfully generated {len(test_cases)} characters of test cases")
            
            return test_cases, generation_context
            
        except Exception as e:
            error_msg = f"Error setting up AI generation: {str(e)}"
            print(f"⚠️ AI generation setup failed: {str(e)}")
            return None, generation_context
    
    def _convert_markdown_to_adf(self, content: str) -> list:
        """Convert markdown-like content to ADF format for Jira rich text fields"""
        blocks = []
        lines = content.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                # Empty line - add a paragraph break
                i += 1
                continue
                
            if line.startswith('### '):
                # H3 header
                blocks.append({
                    "type": "heading",
                    "attrs": {"level": 3},
                    "content": [{"type": "text", "text": line[4:]}]
                })
            elif line.startswith('## '):
                # H2 header
                blocks.append({
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": line[3:]}]
                })
            elif line.startswith('# '):
                # H1 header
                blocks.append({
                    "type": "heading",
                    "attrs": {"level": 1},
                    "content": [{"type": "text", "text": line[2:]}]
                })
            elif line.startswith('**') and line.endswith('**'):
                # Bold text as paragraph
                blocks.append({
                    "type": "paragraph",
                    "content": [{
                        "type": "text",
                        "text": line[2:-2],
                        "marks": [{"type": "strong"}]
                    }]
                })
            elif line.startswith('```'):
                # Code block
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith('```'):
                    code_lines.append(lines[i])
                    i += 1
                
                if code_lines:
                    blocks.append({
                        "type": "codeBlock",
                        "attrs": {"language": "bash"},
                        "content": [{"type": "text", "text": '\n'.join(code_lines)}]
                    })
            elif line.startswith('- ') or line.startswith('* '):
                # Bullet list
                list_items = []
                while i < len(lines) and (lines[i].strip().startswith('- ') or lines[i].strip().startswith('* ')):
                    item_text = lines[i].strip()[2:]
                    list_items.append({
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [{"type": "text", "text": item_text}]
                        }]
                    })
                    i += 1
                i -= 1  # Adjust for the outer loop increment
                
                if list_items:
                    blocks.append({
                        "type": "bulletList",
                        "content": list_items
                    })
            elif line.startswith('---'):
                # Horizontal rule
                blocks.append({"type": "rule"})
            else:
                # Regular paragraph
                if line:
                    blocks.append({
                        "type": "paragraph",
                        "content": [{"type": "text", "text": line}]
                    })
            
            i += 1
        
        return blocks if blocks else [{
            "type": "paragraph",
            "content": [{"type": "text", "text": content}]
        }]
    
    def update_jira_field(self, issue_key: str, field_id: str, content: str) -> bool:
        """Update a Jira field with content"""
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}"
        headers = {
            "Authorization": self.auth_header,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        # Create ADF (Atlassian Document Format) structure for rich text fields
        # Parse markdown-like content and convert to proper ADF format
        content_blocks = self._convert_markdown_to_adf(content)
        
        adf_content = {
            "type": "doc",
            "version": 1,
            "content": content_blocks
        }
        
        payload = {
            "fields": {
                field_id: adf_content
            }
        }
        
        response = requests.put(url, headers=headers, json=payload)
        
        if response.status_code == 204:
            print(f"✅ Successfully updated {field_id} for {issue_key}")
            return True
        else:
            print(f"❌ Error updating {field_id} for {issue_key}: {response.status_code} - {response.text}")
            return False
    
    def process_tickets_with_test_cases(self, jql: str) -> List[Dict[str, Any]]:
        """Fetch tickets and generate test cases for each"""
        tickets = self.fetch_tickets_with_criteria(jql)
        
        if not tickets:
            return []
        
        test_cases_field_id = os.getenv('TEST_CASES_FIELD', 'customfield_11600')
        
        for ticket in tickets:
            print(f"\n🔄 Processing {ticket['key']}...")
            
            # Fetch PR information using GitHub API search
            print(f"🔗 Fetching PR info for {ticket['key']}...")
            pr_info = self.fetch_prs_from_github(ticket['key'])
            
            if pr_info:
                # Fetch code changes for each PR
                for repo, pr in pr_info.items():
                    code_changes = self.fetch_pr_code_changes(pr['url'])
                    if 'error' not in code_changes:
                        pr['code_changes'] = code_changes
                    else:
                        pr['code_changes'] = None
                
                ticket['pull_requests'] = pr_info
                print(f"📋 Found {len(pr_info)} PR(s) across repositories")
                for repo, pr in pr_info.items():
                    print(f"  - {repo}: PR #{pr['number']} ({pr['state']})")
                    if pr.get('code_changes'):
                        changes = pr['code_changes']['summary']
                        print(f"    Code changes: {pr['code_changes']['total_files']} files, +{changes['additions']} -{changes['deletions']}")
            else:
                print(f"  No PR information found")
                ticket['pull_requests'] = {}
            
            # Generate test cases (include PR information if available)
            pr_context = ""
            if pr_info:
                pr_context_parts = []
                for repo, pr in pr_info.items():
                    if pr.get('body') or pr.get('code_changes'):
                        context_part = f"\n\nPULL REQUEST CONTEXT FROM {repo} - PR #{pr['number']}:\nTitle: {pr['title']}\nState: {pr['state']}\nAuthor: {pr['author']}"
                        
                        if pr.get('body'):
                            context_part += f"\nDescription:\n{pr['body']}"
                        
                        # Add code changes if available
                        if pr.get('code_changes'):
                            code_context = self.format_code_changes_for_context(pr['code_changes'])
                            if code_context:
                                context_part += f"\n{code_context}"
                        
                        pr_context_parts.append(context_part)
                
                if pr_context_parts:
                    pr_context = ''.join(pr_context_parts)
                    print(f"📋 Including PR context from {len(pr_context_parts)} repository/repositories for test case generation")
            
            test_cases, generation_context = self.generate_test_cases(ticket, pr_context=pr_context)
            
            if test_cases:
                print(f"📝 Generated test cases for {ticket['key']}")
                
                # Add the context used for test case generation to the ticket data
                ticket['test_case_generation_context'] = generation_context
                
                # Update Jira field
                success = self.update_jira_field(ticket['key'], test_cases_field_id, test_cases)
                
                if success:
                    ticket['test_cases'] = test_cases
                    ticket['test_cases_updated'] = True
                else:
                    ticket['test_cases_updated'] = False
            else:
                print(f"❌ Failed to generate test cases for {ticket['key']}")
                ticket['test_cases_updated'] = False
        
        return tickets
    
    def get_issue_links(self, issue_key: str) -> List[Dict[str, Any]]:
        """Get all links for a Jira issue including PR links"""
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}"
        headers = {
            "Authorization": self.auth_header,
            "Accept": "application/json"
        }
        
        # Request specific fields including issuelinks
        params = {
            "fields": "issuelinks,remotelinks"
        }
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            issue_data = response.json()
            links = []
            
            # Process issue links (internal Jira links)
            for link in issue_data.get('fields', {}).get('issuelinks', []):
                if 'outwardIssue' in link:
                    links.append({
                        'type': 'issue_link',
                        'relationship': link.get('type', {}).get('outward', 'related to'),
                        'key': link['outwardIssue']['key'],
                        'summary': link['outwardIssue']['fields']['summary'],
                        'status': link['outwardIssue']['fields']['status']['name']
                    })
                elif 'inwardIssue' in link:
                    links.append({
                        'type': 'issue_link', 
                        'relationship': link.get('type', {}).get('inward', 'related to'),
                        'key': link['inwardIssue']['key'],
                        'summary': link['inwardIssue']['fields']['summary'],
                        'status': link['inwardIssue']['fields']['status']['name']
                    })
            
            return links
        else:
            print(f"Error fetching links for {issue_key}: {response.status_code} - {response.text}")
            return []
    
    def fetch_prs_from_github(self, issue_key: str) -> Dict[str, Dict[str, Any]]:
        """Fetch PRs from GitHub using search API by ticket key in title"""
        github_token = os.getenv('GITHUB_TOKEN')
        if not github_token:
            print(f"⚠️ GITHUB_TOKEN not found in environment variables")
            return {}
        
        # GitHub search API endpoint
        search_url = "https://api.github.com/search/issues"
        
        # Search query: find PRs with the ticket key in title
        query = f"{issue_key} in:title type:pr"
        
        headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Jira-Ticket-Fetcher'
        }
        
        params = {
            'q': query
        }
        
        try:
            print(f"🔍 Searching GitHub for PRs with '{issue_key}' in title...")
            response = requests.get(search_url, headers=headers, params=params)
            
            if response.status_code == 200:
                search_data = response.json()
                items = search_data.get('items', [])
                
                if not items:
                    print(f"   No PRs found for {issue_key}")
                    return {}
                
                print(f"   Found {len(items)} PR(s) for {issue_key}")
                
                # Group PRs by repository
                repos_prs = {}
                for item in items:
                    repo_full_name = item.get('repository_url', '').replace('https://api.github.com/repos/', '')
                    if not repo_full_name:
                        continue
                    
                    pr_data = {
                        'number': item.get('number'),
                        'title': item.get('title'),
                        'url': item.get('html_url'),
                        'state': item.get('state'),
                        'author': item.get('user', {}).get('login'),
                        'created_at': item.get('created_at'),
                        'updated_at': item.get('updated_at'),
                        'body': item.get('body', ''),
                        'repository': repo_full_name
                    }
                    
                    if repo_full_name not in repos_prs:
                        repos_prs[repo_full_name] = []
                    repos_prs[repo_full_name].append(pr_data)
                
                # For each repository, keep only the PR with lowest ID that is not declined
                selected_prs = {}
                for repo, prs in repos_prs.items():
                    # Sort by PR number (ascending) to get lowest ID first
                    sorted_prs = sorted(prs, key=lambda x: x.get('number', 0))
                    
                    for pr in sorted_prs:
                        # Skip declined PRs (closed without being merged)
                        if pr.get('state') == 'closed':
                            # We need to check if it was merged by fetching detailed PR info
                            detailed_pr = self._get_detailed_pr_info(pr['url'])
                            if detailed_pr and not detailed_pr.get('merged_at'):
                                print(f"   Skipping declined PR #{pr['number']} in {repo}")
                                continue
                        
                        # This is the lowest ID non-declined PR for this repo
                        selected_prs[repo] = pr
                        print(f"   Selected PR #{pr['number']} from {repo} (state: {pr['state']})")
                        break
                
                return selected_prs
                
            elif response.status_code == 403:
                print(f"❌ GitHub API rate limited or access denied")
                return {}
            else:
                print(f"❌ GitHub search API error: {response.status_code} - {response.text[:200]}")
                return {}
                
        except Exception as e:
            print(f"❌ Error searching GitHub for PRs: {str(e)}")
            return {}
    
    def _get_detailed_pr_info(self, pr_url: str) -> Dict[str, Any]:
        """Get detailed PR info to check if it was merged"""
        import re
        
        # Extract owner, repo, and PR number from URL
        match = re.match(r'https://github\.com/([^/]+)/([^/]+)/pull/(\d+)', pr_url)
        if not match:
            return {}
        
        owner, repo, pr_number = match.groups()
        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        
        github_token = os.getenv('GITHUB_TOKEN')
        headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Jira-Ticket-Fetcher'
        }
        
        try:
            response = requests.get(api_url, headers=headers)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"   Error fetching detailed PR info: {str(e)}")
        
        return {}
    
    def fetch_pr_code_changes(self, pr_url: str) -> Dict[str, Any]:
        """Fetch code changes (diff) from GitHub PR"""
        import re
        
        # Extract owner, repo, and PR number from URL
        match = re.match(r'https://github\.com/([^/]+)/([^/]+)/pull/(\d+)', pr_url)
        if not match:
            return {'error': 'Invalid GitHub PR URL format'}
        
        owner, repo, pr_number = match.groups()
        
        # GitHub API endpoint for PR files
        files_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
        
        github_token = os.getenv('GITHUB_TOKEN')
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Jira-Ticket-Fetcher'
        }
        
        if github_token:
            headers['Authorization'] = f'token {github_token}'
        
        try:
            print(f"🔍 Fetching code changes for PR #{pr_number}...")
            response = requests.get(files_url, headers=headers)
            
            if response.status_code == 200:
                files_data = response.json()
                
                code_changes = {
                    'total_files': len(files_data),
                    'files': [],
                    'summary': {
                        'additions': 0,
                        'deletions': 0,
                        'changes': 0
                    }
                }
                
                for file_data in files_data:
                    file_info = {
                        'filename': file_data.get('filename'),
                        'status': file_data.get('status'),  # added, modified, deleted, renamed
                        'additions': file_data.get('additions', 0),
                        'deletions': file_data.get('deletions', 0),
                        'changes': file_data.get('changes', 0),
                        'patch': file_data.get('patch', ''),  # The actual code diff
                        'blob_url': file_data.get('blob_url'),
                        'raw_url': file_data.get('raw_url')
                    }
                    
                    # Update totals
                    code_changes['summary']['additions'] += file_info['additions']
                    code_changes['summary']['deletions'] += file_info['deletions']
                    code_changes['summary']['changes'] += file_info['changes']
                    
                    code_changes['files'].append(file_info)
                
                print(f"   ✅ Found {code_changes['total_files']} files, +{code_changes['summary']['additions']} -{code_changes['summary']['deletions']} lines")
                return code_changes
                
            elif response.status_code == 404:
                print(f"   ❌ PR files not found")
                return {'error': 'PR files not found', 'status_code': 404}
            elif response.status_code == 403:
                print(f"   ❌ Rate limited or access denied for PR files")
                return {'error': 'Access denied or rate limited', 'status_code': 403}
            else:
                print(f"   ❌ GitHub API error: {response.status_code}")
                return {'error': f'GitHub API error: {response.status_code}'}
                
        except Exception as e:
            print(f"   ❌ Error fetching PR code changes: {str(e)}")
            return {'error': str(e)}
    
    def format_code_changes_for_context(self, code_changes: Dict[str, Any], max_length: int = 8000) -> str:
        """Format code changes for inclusion in test case generation context"""
        if 'error' in code_changes or not code_changes.get('files'):
            return ""
        
        context = f"""
CODE CHANGES SUMMARY:
- Files changed: {code_changes['total_files']}
- Additions: +{code_changes['summary']['additions']} lines
- Deletions: -{code_changes['summary']['deletions']} lines
- Total changes: {code_changes['summary']['changes']} lines

DETAILED FILE CHANGES:
"""
        
        current_length = len(context)
        
        for file_info in code_changes['files']:
            file_header = f"""
📁 {file_info['filename']} ({file_info['status']})
   +{file_info['additions']} -{file_info['deletions']} changes

"""
            
            # Check if we have space for this file
            if current_length + len(file_header) > max_length:
                context += f"\n... (truncated - remaining files not shown)"
                break
            
            context += file_header
            current_length += len(file_header)
            
            # Add patch/diff if it fits
            patch = file_info.get('patch', '')
            if patch:
                # Limit patch size to avoid overwhelming the context
                max_patch_length = min(2000, max_length - current_length - 100)
                if len(patch) > max_patch_length:
                    patch = patch[:max_patch_length] + "\n... (truncated)"
                
                patch_section = f"```diff\n{patch}\n```\n"
                
                if current_length + len(patch_section) <= max_length:
                    context += patch_section
                    current_length += len(patch_section)
                else:
                    context += "```\n(Code diff too large to include)\n```\n"
                    break
        
        return context

def main():
    # Load environment variables from .env file
    from dotenv import load_dotenv
    load_dotenv()
    
    # Get credentials from environment variables
    jira_url = "https://consumeraffairs.atlassian.net"
    email = os.getenv('JIRA_EMAIL')
    api_token = os.getenv('JIRA_API_TOKEN')
    
    if not email or not api_token:
        print("❌ Error: JIRA_EMAIL and JIRA_API_TOKEN must be set in .env file")
        print("Please check your .env file contains:")
        print("JIRA_EMAIL=your-email@consumeraffairs.com")
        print("JIRA_API_TOKEN=your-jira-api-token")
        return
    
    # Initialize fetcher
    fetcher = JiraTicketFetcher(jira_url, email, api_token)
    
    # Get JQL query from environment variable or user input
    jql_query = os.getenv('JQL_QUERY')
    if not jql_query:
        jql_query = input("Enter your JQL query (or press Enter for default): ").strip()
        if not jql_query:
            jql_query = "project = CA AND status != Done ORDER BY created DESC"
    
    # Check if we're in preview mode
    preview_mode = os.getenv('PREVIEW_MODE', 'false').lower() == 'true'
    
    if preview_mode:
        # Preview mode: just fetch basic ticket info and display
        print("Fetching ticket information...")
        tickets = fetcher.fetch_tickets_with_criteria(jql_query)
        
        if tickets:
            print(f"✅ Found {len(tickets)} ticket(s):")
            print("=" * 60)
            
            for i, ticket in enumerate(tickets, 1):
                print(f"{i}. {ticket['key']} - {ticket['summary']}")
                print(f"   Status: {ticket['status']} | Assignee: {ticket['assignee']}")
                print("")
                
            print("=" * 60)
        else:
            print("❌ No tickets found matching the JQL query.")
            exit(1)
    else:
        # Full mode: process with test case generation
        print(f"Searching for tickets with JQL: {jql_query}")
        
        # Check if we should generate test cases
        generate_test_cases = os.getenv('GENERATE_TEST_CASES', 'false').lower() == 'true'
        
        if generate_test_cases:
            print("🤖 AI test case generation enabled")
            print("Fetching tickets and generating test cases...")
            
            tickets = fetcher.process_tickets_with_test_cases(jql_query)
        else:
            print("Fetching tickets...")
            tickets = fetcher.fetch_tickets_with_criteria(jql_query)
        
        if tickets:
            fetcher.print_tickets(tickets)
            
            # Automatically save to JSON file in non-preview mode
            filename = "jira_tickets.json"
            with open(filename, 'w') as f:
                json.dump(tickets, f, indent=2, default=str)
            print(f"Results automatically saved to {filename}")
        else:
            print("No tickets found or error occurred.")
            exit(1)

if __name__ == "__main__":
    main()