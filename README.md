# TeachMate 🎓🤖

TeachMate is an **AI-powered Education Management System** designed to simplify assignment creation, submission, grading, and analytics for educational environments. It supports **teachers, students, and admins**, with advanced **AI-based features** such as automatic assignment generation, plagiarism detection, similarity checking, AI-driven grading, and analytics dashboards.

---

## 🚀 Key Highlights

* AI-based assignment creation
* AI-powered grading and feedback
* Plagiarism & similarity checking
* Role-Based Access Control (RBAC)
* Analytics dashboards for insights
* Supports multi-role users (teacher + student)

---

## 👥 User Roles & Capabilities

### 👨‍🎓 Student

* Enroll in multiple classes
* View assigned assignments
* Submit answers (text/files)
* View grades and AI-generated feedback
* Track performance via analytics

### 👨‍🏫 Teacher

* Teach multiple classes and subjects
* Create assignments manually or using AI
* Define rubrics and grading criteria
* View student submissions
* Use AI-based grading and plagiarism/similarity reports
* Monitor class performance through analytics

### 🛡️ Admin

* Manage users (students, teachers, admins)
* Create and manage classes
* Assign teachers to classes
* Enroll students in classes
* View system-wide analytics
* Resolve role or permission issues

---

## 🧠 AI-Powered Features

### 1. AI-Based Assignment Creation

* Generate assignments from topics, difficulty level, and question count
* Supports descriptive, MCQ, and conceptual questions
* Saves time for teachers

### 2. AI-Based Grading

* Automatically evaluates student submissions
* Uses rubrics defined by the teacher
* Generates consistent scores and feedback

### 3. Plagiarism & Similarity Checking

* Detects copied or highly similar submissions
* Compares submissions within the same class
* Generates similarity percentages and reports

### 4. Analytics Dashboard

* Student performance trends
* Class-level insights
* Assignment difficulty analysis
* Submission and grading statistics

---

## 🧱 System Architecture

```
Frontend (React + TypeScript)
        |
        | REST API
        v
Backend (FastAPI + Python)
        |
        | Supabase SDK
        v
Database (PostgreSQL - Supabase)
        |
        v
AI Services (LLMs, Similarity Models)
```

---

## 🛠️ Tech Stack

### Backend

* Python
* FastAPI
* Supabase (Auth + Database)
* JWT Authentication
* RBAC Middleware

### Frontend

* React
* TypeScript
* Tailwind / CSS
* Charts & Analytics Libraries

### AI & Data

* LLMs for assignment generation & grading
* Text similarity & plagiarism detection models
* Analytics processing

---

## 🔐 Authentication & Authorization

* Supabase Authentication (JWT-based)
* Role-Based Access Control (RBAC)
* A single user can have **multiple roles** (Teacher + Student)
* Admin-only protected routes

---

## 📂 Project Structure

```
teachmate/
│── backend/
│   ├── main.py
│   ├── auth.py
│   ├── db_helpers.py
│   ├── ai_services/
│   └── models/
│
│── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── api/
│   │   └── dashboards/
│
│── README.md
│── requirements.txt
│── .env.example
```

---

## ⚙️ Setup Instructions

### 1. Clone Repository

```bash
git clone https://github.com/your-username/teachmate.git
cd teachmate
```

### 2. Backend Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file:

```env
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_role_key
```

Run backend:

```bash
uvicorn main:app --reload
```

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

---

## 🧑‍💼 Creating an Admin User

1. Register a normal user
2. In Supabase database, update the user's role to `admin`
3. Log in again → Admin Dashboard will appear

---

## 📊 Analytics Examples

* Average grades per class
* Submission timelines
* AI grading distribution
* Plagiarism similarity heatmaps

---

## 🔮 Future Enhancements

* Real-time notifications
* AI tutor/chat assistant
* Peer review system
* LMS integrations (Google Classroom, Moodle)
* Advanced plagiarism detection across semesters

---

## 🤝 Contributions

Contributions are welcome! Please fork the repository and submit a pull request.

---

## 📜 License

This project is licensed under the MIT License.

---

## ⭐ Acknowledgements

* Supabase
* FastAPI
* React
* AI/LLM technologies

---

**TeachMate — Smart Education Powered by AI** 🚀

