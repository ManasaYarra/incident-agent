# 🚨 Incident Response Agent with Memory

An AI-powered **on-call assistant** that remembers past software incidents, their root causes, resolution steps, and outcomes using **Hindsight memory**.

When a new incident occurs, the agent recalls similar historical incidents and provides relevant troubleshooting guidance using a **Groq-powered LLM**. Engineers can then record whether the suggested resolution **worked or failed**, allowing the system to build useful incident-response history for future incidents.

---

## 🎯 Problem

When a production incident occurs, engineers often spend valuable time investigating problems that may have already happened before.

They may need to search through:

- Previous incident logs
- Root-cause investigations
- Troubleshooting notes
- Previous fixes
- Incident outcomes

This can lead to repeated troubleshooting and slower incident resolution.

### Our Solution

The **Incident Response Agent** gives an AI assistant access to historical incident knowledge.

Instead of treating every incident as a completely new problem, the agent can:

1. Receive a new error log.
2. Recall similar incidents from Hindsight memory.
3. Analyze previous root causes and fixes.
4. Generate a relevant troubleshooting suggestion using an LLM.
5. Allow the engineer to test the suggested resolution.
6. Record whether the resolution worked or failed.
7. Use the incident history when similar problems occur again.

---

## 🧠 How It Works

```text
                    New Incident
                         │
                         ▼
                 ┌───────────────┐
                 │   Error Log    │
                 └───────┬───────┘
                         │
                         ▼
                ┌──────────────────┐
                │ Hindsight Memory │
                │     Recall       │
                └────────┬─────────┘
                         │
                         ▼
                Similar Past Incidents
                         │
                         ▼
                ┌──────────────────┐
                │    Groq LLM      │
                │  gpt-oss-120b    │
                └────────┬─────────┘
                         │
                         ▼
                 Suggested Fix
                         │
                         ▼
                 Engineer Tests Fix
                         │
                 ┌───────┴────────┐
                 ▼                ▼
              Worked            Failed
                 │                │
                 └───────┬────────┘
                         ▼
                 Incident History
```

---

## ✨ Key Features

### 🔍 Similar Incident Recall

The agent searches historical incidents to find problems that are similar to the current error log.

### 🧠 Persistent Memory

Each incident can contain:

- Error log
- Root cause
- Resolution/fix
- Outcome

This gives the AI access to previous troubleshooting experiences.

### 🤖 AI-Powered Troubleshooting

The retrieved incident history is used as context for the Groq LLM to generate a relevant troubleshooting suggestion.

### ✅ Outcome Tracking

Engineers can mark a resolution as **Worked** or **Failed**. This outcome becomes part of the incident history.

### 🚫 Failed-Fix Filtering

Failed fixes are excluded from future suggestions so that the system does not blindly recommend approaches that previously failed.

### 📚 Ready-to-Demo Incident History

The project includes realistic simulated backend incidents so that the agent already has historical knowledge when the demonstration begins.

---

## 🏗️ System Architecture

```text
┌───────────────────────┐
│       Engineer        │
│   Pastes Error Log    │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│    Streamlit UI       │
│       app.py          │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│  Incident Response    │
│       Agent           │
└───────┬───────────────┘
        │
        ├──────────────────────┐
        ▼                      ▼
┌───────────────┐      ┌────────────────┐
│   Hindsight   │      │    Groq LLM    │
│    Memory     │      │  gpt-oss-120b  │
└───────┬───────┘      └───────┬────────┘
        │                      │
        │ Similar incidents    │
        └──────────┬───────────┘
                   ▼
          ┌─────────────────┐
          │ Suggested Fix   │
          └────────┬────────┘
                   │
                   ▼
          ┌─────────────────┐
          │ Worked / Failed │
          └────────┬────────┘
                   │
                   ▼
          ┌─────────────────┐
          │ Incident Memory │
          └─────────────────┘
```

---

## 🛠️ Tech Stack

| Technology | Purpose |
|---|---|
| **Python** | Core application logic |
| **Streamlit** | Interactive web interface |
| **Hindsight Cloud** | Long-term incident memory |
| **Groq** | LLM inference |
| **openai/gpt-oss-120b** | AI-powered troubleshooting |
| **Git & GitHub** | Version control and collaboration |

---

## 📁 Project Structure

```text
incident-response-agent/
│
├── app.py
├── memory.py
├── fake_data.py
├── load_data.py
├── requirements.txt
├── README.md
├── .env.example
├── .gitignore
│
└── ...
```

### File Overview

| File | Purpose |
|---|---|
| `app.py` | Streamlit application and user interface |
| `memory.py` | Hindsight memory operations |
| `fake_data.py` | Simulated backend incident dataset |
| `load_data.py` | Loads incident history into Hindsight |
| `requirements.txt` | Python dependencies |
| `.env.example` | Example environment-variable configuration |
| `.gitignore` | Prevents sensitive/unnecessary files from being committed |
| `README.md` | Project documentation |

---

## 📊 Incident Data

The project uses simulated backend incidents covering different types of software problems, including:

- Database issues
- Memory leaks
- API timeouts
- Deployment failures
- Third-party service outages

The seed dataset gives the agent historical knowledge from the beginning of the demonstration.

> **Note:** The incident data is simulated and does not contain real production logs or confidential information.

---

## 🧾 Incident Data Format

An incident contains information such as:

```python
{
    "log": "502 Bad Gateway on checkout API, spike at 9PM",
    "root_cause": "Backend pods crashed due to a memory leak",
    "fix": "Restarted pods and increased memory limits",
    "outcome": "worked"
}
```

This structured information allows the system to connect new incidents with previous troubleshooting experiences.

---

## 🔄 Hindsight Memory

Hindsight is used as the project's long-term memory layer.

### Retain

When an incident is recorded, the system stores information about:

```text
Error Log
    +
Root Cause
    +
Fix
    +
Outcome
```

### Recall

When a new incident is submitted, the system searches its historical memory for relevant incidents.

```text
New Error
    ↓
Hindsight Recall
    ↓
Similar Incidents
    ↓
Previous Fixes & Outcomes
    ↓
LLM Context
    ↓
Suggested Troubleshooting
```

Failed fixes are excluded from future suggestions according to the current project workflow.

---

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/incident-response-agent.git
cd incident-response-agent
```

### 2. Create a Virtual Environment

For Windows:

```powershell
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create your local `.env` file from the example:

```powershell
copy .env.example .env
```

Then add the required API credentials to `.env`.

**Never commit `.env` to GitHub.**

### 5. Load the Incident History

```bash
python load_data.py
```

This seeds Hindsight memory with the project's simulated historical incidents.

### 6. Start the Application

```bash
streamlit run app.py
```

The Streamlit application will start locally.

---

## 🧪 Example

### Input

```text
502 Bad Gateway on checkout API.
Traffic increased significantly around 9 PM.
```

### Agent Process

```text
1. Receive incident
       ↓
2. Search Hindsight memory
       ↓
3. Find similar historical incidents
       ↓
4. Analyze previous fixes
       ↓
5. Generate troubleshooting suggestion
       ↓
6. Engineer tests the resolution
       ↓
7. Mark Worked / Failed
```

### Result

The agent can use relevant historical incidents to provide context instead of treating the problem as completely new.

---

## 🔐 Security

Sensitive credentials should never be committed to the repository.

The `.gitignore` file should include:

```gitignore
.env
venv/
.venv/
__pycache__/
*.pyc
```

Before pushing changes to GitHub, verify:

```bash
git status
```

Make sure your `.env` file is not listed as a file to be committed.

---

## 🧑‍💻 GitHub Workflow

For contributors:

```bash
git pull
git add .
git commit -m "Update incident memory and documentation"
git push
```

For the initial repository setup:

```bash
git init
git add .
git commit -m "Initial Incident Response Agent"
git branch -M main
git remote add origin https://github.com/yourusername/incident-response-agent.git
git push -u origin main
```

---

## 🎯 Project Goals

The project demonstrates how AI and persistent memory can support software incident response by:

- Reducing repeated troubleshooting effort
- Making previous incident knowledge easier to retrieve
- Providing context-aware troubleshooting suggestions
- Preserving successful troubleshooting approaches
- Recording unsuccessful approaches
- Building reusable incident-response knowledge
- Demonstrating the practical use of long-term AI memory

---

## 🔮 Future Improvements

The prototype can be extended with:

- Real production log ingestion
- Automatic incident classification
- Root-cause analysis
- Incident severity detection
- Slack or Microsoft Teams integration
- Jira/ServiceNow integration
- Monitoring and observability integrations
- Automatic incident summaries
- Incident timeline generation
- Advanced semantic retrieval
- Human-approved automated remediation
- Incident analytics and dashboards

---

## ⚠️ Disclaimer

This project is a **hackathon prototype** created for educational and demonstration purposes.

The incident dataset is simulated and should not be considered real production incident information.

AI-generated troubleshooting suggestions should be reviewed and validated by an engineer before being applied to production systems.

---

## 👥 Team

Developed collaboratively as part of a hackathon project.

### Data + GitHub Lead

Responsibilities include:

- Preparing realistic simulated incident data
- Building the initial incident knowledge base
- Loading incidents into Hindsight memory
- Maintaining the GitHub repository
- Managing Git workflow
- Maintaining project documentation
- Ensuring sensitive configuration files are not committed

---

## 📄 License

This project is developed for educational and hackathon purposes.
