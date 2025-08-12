# 🎯 Jira Test Case Generator

An intelligent automation tool that generates comprehensive test cases for Jira tickets by analyzing ticket details, GitHub pull requests, and actual code changes using AI.

## ✨ Features

- **🔍 Smart Ticket Fetching**: Uses JQL queries to fetch tickets from Jira with custom field support
- **🔗 GitHub Integration**: Automatically finds related PRs using GitHub search API
- **📁 Code Analysis**: Fetches and analyzes actual code changes, diffs, and file modifications
- **🤖 AI-Powered Test Generation**: Uses Claude AI to generate comprehensive, implementation-specific test cases
- **📝 Automatic Jira Updates**: Writes generated test cases directly to Jira's "Test Instructions" field
- **📊 Comprehensive Reporting**: Saves detailed JSON output with all ticket and PR data

## 🚀 What It Does

The tool automatically:

1. **Fetches Jira tickets** based on your JQL filter
2. **Finds related GitHub PRs** by searching for ticket keys in PR titles
3. **Analyzes code changes** including file diffs, additions, deletions
4. **Generates intelligent test cases** using AI with comprehensive context
5. **Updates Jira tickets** with test cases in the "Test Instructions" field
6. **Saves complete results** to JSON for further analysis

## 📋 Prerequisites

- **Python 3.10+** (required for union type syntax)
- Jira API access with appropriate permissions
- GitHub API access (personal access token)
- Claude API access (Anthropic API key)
- Access to ConsumerAffairs Jira instance

### Python Setup (macOS)

Check your Python version:
```bash
python3 --version
```

**If you don't have Python installed:**
```bash
# Install Homebrew first (if not already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Then install Python
brew install python
```

**Or download from official site:**
- Download Python 3.10+ from [python.org](https://www.python.org/downloads/macos/)
- Run the installer

**If you have Python < 3.10, update it:**
```bash
# Using Homebrew
brew install python@3.10

# Using pyenv
pyenv install 3.10.12
pyenv global 3.10.12
```

## 📦 Installation

1. Clone the repository:
```bash
git clone https://github.com/laquinoCA/jira-qa-wizard.git
cd jira-qa-wizard
```

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

## ⚙️ Configuration

### 1. Environment Setup

Create a `.env` file in the project root with the following configuration:

```env
# Jira Configuration
JIRA_EMAIL=your-email@consumeraffairs.com
JIRA_API_TOKEN=your-jira-api-token

# Anthropic API Configuration  
ANTHROPIC_API_KEY=your-claude-api-key

# GitHub Configuration
GITHUB_TOKEN=your-github-personal-access-token

# Jira Custom Field Configuration
DESCRIPTION_FIELD=customfield_12881
ACCEPTANCE_CRITERIA_FIELD=customfield_12819
TEST_CASES_FIELD=customfield_11600

# Feature Flags
GENERATE_TEST_CASES=true
FETCH_PRS=true
PREVIEW_MODE=false
```

### 2. API Token Setup

#### Jira API Token
1. Go to [Atlassian API Tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Create a new API token
3. Copy the token to `JIRA_API_TOKEN` in your `.env` file

#### GitHub Personal Access Token
1. Go to [GitHub Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens)
2. Generate a new token with `repo` and `public_repo` scopes
3. Copy the token to `GITHUB_TOKEN` in your `.env` file

#### Claude API Key
1. Go to [Anthropic Console](https://console.anthropic.com/)
2. Create a new API key
3. Copy the key to `ANTHROPIC_API_KEY` in your `.env` file

## 🏃‍♂️ Usage

### Interactive Mode

Run the script interactively and enter your JQL query when prompted:

```bash
./run_jira_fetch.sh
```

### Command Line Mode

Set the JQL query as an environment variable:

```bash
JQL_QUERY='your-jql-query-here' ./run_jira_fetch.sh
```

### Direct Python Execution

```bash
export JQL_QUERY='your-jql-query-here'
export PREVIEW_MODE="false"
export GENERATE_TEST_CASES="true"
python3 jira_ticket_fetcher.py
```

## 📝 JQL Query Examples

### Basic Queries
```jql
# All Ready for QA tickets in PDW project
project = PDW AND status = "Ready for QA"

# Tickets assigned to specific QA engineer
project = PDW AND "QA Assigned[User Picker (single user)]" = 613f7a83eaef340069607d41

# Platform team tickets ready for QA
project = PDW AND "Sprint Team[Dropdown]" = Platform AND status = "Ready for QA"

# Specific ticket keys
key in (PDW-9468, PDW-9469, PDW-9470)

# Recent tickets
project = PDW AND created >= -7d AND status != Done
```

### Advanced Queries
```jql
# Combined filters
project = PDW AND "Sprint Team[Dropdown]" = Platform 
AND "QA Assigned[User Picker (single user)]" = 613f7a83eaef340069607d41 
AND status = "Ready for QA"

# Tickets updated recently
project = PDW AND updated >= -3d AND status in ("Ready for QA", "In QA")

# Tickets by assignee
project = PDW AND assignee = currentUser() AND status != Done
```

## 🧠 Test Case Generation Context

The AI receives comprehensive context for generating test cases:

### 1. **Jira Ticket Information**
- **Ticket Key**: PDW-XXXX
- **Summary**: Brief ticket description
- **Description**: Full ticket description from custom field
- **Acceptance Criteria**: Detailed criteria from custom field

### 2. **GitHub Pull Request Data**
- **PR Title & Description**: Complete PR information
- **PR State**: Open, closed, merged status
- **Author Information**: Who created the PR
- **Repository Details**: Which repo the changes are in

### 3. **Developer Testing Guidance**
- **Manual Test Instructions**: Developer-provided testing steps
- **Test Scenarios**: Specific test cases from PR descriptions
- **Shell Commands**: Commands developers recommend
- **Testing Approach**: How developers suggest verifying the implementation

### 4. **Code Change Analysis**
- **File Changes**: Lists of modified, added, deleted files
- **Code Diffs**: Actual code changes with line-by-line diffs
- **Change Statistics**: Lines added, removed, total changes
- **File-specific Details**: Per-file change breakdowns

### 5. **Multi-Repository Support**
For tickets spanning multiple repositories (like microservices), the tool:
- Finds PRs across all relevant repositories
- Selects one PR per repository (lowest ID, non-declined)
- Includes code changes from all selected PRs
- Provides comprehensive cross-repo context

## 🎯 QA Environment Integration

Test cases are generated specifically for QA environment constraints:

### **Environment Considerations**
- **No Direct Database Access**: Uses Django admin interface instead of SQL queries
- **Admin Interface Navigation**: Provides exact admin URLs like `/admin/sessions/session/`
- **Log Monitoring**: Uses standard monitoring tools instead of direct log access
- **Authentication**: Considers QA environment security and access patterns

### **Test Case Quality**
- **Developer-Guided**: Incorporates testing instructions from PR descriptions
- **Implementation-Specific**: References actual class names, methods, and code changes
- **Actionable Steps**: Clear, executable instructions for QA engineers
- **Environment-Appropriate**: Realistic for QA constraints and available tools

## 📤 Output

### Console Output
- Real-time progress updates
- Ticket summaries with PR information
- Code change statistics
- AI generation status
- Error handling and warnings

### Jira Updates
- Test cases written to **"Test Instructions"** field in the **QA Tab**
- Uses custom field ID: `customfield_11600`
- Formatted as structured test cases with steps and expected results

### JSON Export
Complete results saved to `jira_tickets.json`:
```json
{
  "key": "PDW-XXXX",
  "summary": "Ticket summary",
  "description": "Full description",
  "acceptance_criteria": "Detailed criteria",
  "pull_requests": {
    "repository-name": {
      "number": 123,
      "title": "PR title",
      "body": "PR description",
      "code_changes": {
        "total_files": 5,
        "summary": {
          "additions": 150,
          "deletions": 25
        },
        "files": [...]
      }
    }
  },
  "test_cases": "Generated test cases",
  "test_case_generation_context": "Full context used"
}
```

## 🔧 Script Modes

### Preview Mode
```bash
export PREVIEW_MODE="true"
```
- Shows found tickets without generating test cases
- Useful for verifying your JQL query
- No Jira updates performed

### Full Generation Mode
```bash
export PREVIEW_MODE="false"
export GENERATE_TEST_CASES="true"
```
- Fetches complete ticket data
- Generates and uploads test cases
- Updates Jira fields
- Saves comprehensive JSON output

## 💎 Advanced Test Case Features

### **Developer-Driven Testing**
- **Incorporates PR Testing Guidance**: Automatically finds and includes developer testing instructions from PR descriptions
- **Exact Command Integration**: Uses specific shell commands, imports, and code snippets that developers provide
- **Real Testing Scenarios**: Converts developer "Manual Test Instructions" into structured QA test cases

### **QA Environment Optimized**
- **Django Admin Focus**: Uses admin interface navigation instead of direct database queries
- **Realistic Access Patterns**: Considers actual QA environment constraints and available tools
- **Environment-Specific URLs**: Provides exact admin paths like `/admin/sessions/session/`
- **Monitoring Tool Integration**: Uses standard log monitoring instead of direct file access

### **Implementation-Aware Quality**
- **Code-Specific References**: Mentions actual class names, methods, and implementation details
- **Multi-Repository Support**: Handles tickets spanning multiple applications with coordinated testing
- **Change-Focused Testing**: Directly tests the specific code changes and their impacts
- **Comprehensive Coverage**: Includes positive/negative scenarios, edge cases, and regression testing

## 🚨 Troubleshooting

### Common Issues

1. **"No JQL query provided"**
   - Ensure you're providing a JQL query either interactively or via environment variable

2. **"GITHUB_TOKEN not found"**
   - Add your GitHub personal access token to the `.env` file

3. **"Rate limited or access denied"**
   - Check your GitHub token permissions and rate limits
   - Ensure your Jira API token has sufficient permissions

4. **"No PRs found"**
   - PRs must have the ticket key (e.g., PDW-1234) in their title
   - Check that PRs exist and are publicly accessible

5. **"AI generation failed"**
   - Verify your Claude API key is valid and has sufficient credits
   - Check if the context size exceeds limits

### Debug Tips

- Run in preview mode first to verify ticket fetching
- Check the JSON output for detailed error information
- Monitor API rate limits for GitHub and Jira
- Verify custom field IDs match your Jira configuration

## 🛠️ Technical Details

### Architecture
- **Python 3.7+** with requests, anthropic, and python-dotenv
- **Jira REST API v3** for ticket operations
- **GitHub REST API v3** for PR and code change data
- **Claude 3.5 Sonnet** for AI-powered test case generation

### Performance
- Processes multiple tickets in sequence
- Caches GitHub API responses to minimize rate limit impact
- Optimizes context size to balance detail and API limits
- Handles network errors with retries and graceful degradation

### Security
- All API keys stored in `.env` file (not committed to git)
- Uses secure authentication methods for all API calls
- No sensitive data logged or exposed in output

## 🎨 Customizing Test Case Generation

Want better test cases? Try modifying the AI prompt in `jira_ticket_fetcher.py` around line 441. You can:

- Add your specific QA environment details (URLs, tools, access patterns)
- Focus on particular testing types (regression, edge cases, performance)
- Adjust the test case format and detail level
- Match your team's testing style and communication

## 📈 Example Workflow

1. **QA Engineer** runs script with JQL filter for ready tickets
2. **Script** finds tickets and their associated GitHub PRs
3. **AI** analyzes ticket requirements and code implementation
4. **Generated test cases** cover both functional and technical aspects
5. **Jira** is automatically updated with comprehensive test instructions
6. **QA Engineer** has detailed, implementation-aware test cases ready to execute

---

**Happy Testing!** 🎉

For questions or issues, please check the troubleshooting section or contact the development team.