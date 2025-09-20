# 🍲 Smart Recipe App

A full-stack Django web application that enables users to create, manage, and explore recipes with ease. This project was developed as a final project for a Full Stack Web Application Development course.

### 🌍 **Live App:** [smart-recipe-app-b3x7.onrender.com](https://smart-recipe-app-b3x7.onrender.com)

---

## 📋 Table of Contents

- [📖 Project Overview](#-project-overview)
- [🚀 Features](#-features)
- [📸 Screenshots](#-screenshots)
- [🛠️ Tech Stack](#️-tech-stack)
- [🗂️ Project Structure](#️-project-structure)
- [⚙️ Getting Started](#️-getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation & Setup](#installation--setup)
- [☁️ Deployment](#️-deployment)
- [🧪 Running Tests](#-running-tests)
- [🛡️ Security Highlights](#️-security-highlights)
- [📅 Roadmap](#-roadmap--future-enhancements)
- [✨ Credits](#-credits)

---

## 📖 Project Overview

The Smart Recipe App is a comprehensive web platform where users can securely manage their personal recipe collection. It demonstrates a full-stack development cycle, from back-end logic with Django and a PostgreSQL database to a responsive front-end built with Bootstrap.

**Key capabilities include:**
* Secure user registration and authentication.
* Full CRUD (Create, Read, Update, Delete) functionality for recipes.
* Image uploads with a graceful fallback to a default image.
* Categorization using tags and detailed cooking instructions.
* A responsive, mobile-first design for a seamless experience on any device.

---

## 🚀 Features

### 🔐 Authentication & Security
-   **User Management:** Secure user registration, login, and logout powered by Django's built-in authentication system.
-   **Password Security:** Passwords are automatically hashed, ensuring they are never stored in plaintext.
-   **CSRF Protection:** All forms are protected against Cross-Site Request Forgery attacks.
-   **Permission Control:** Users can only edit or delete their own recipes.

### 📖 Recipe Management (CRUD)
-   **Create:** Add new recipes with a title, description, cooking time, tags, instructions, and an optional image.
-   **Read:** View all recipes on a central dashboard or see individual recipes on a detailed view page.
-   **Update:** Easily edit existing recipes through a dedicated form.
-   **Delete:** Remove recipes that are no longer needed.

### 📱 Responsive Front-End
-   **Mobile-First Design:** Built with Bootstrap 5, the UI is fully responsive and looks great on desktops, tablets, and mobile phones.
-   **Intuitive Navigation:** A clean and simple interface with a collapsible navbar for smaller screens.

---

## 📸 Screenshots

*(Replace the placeholder paths with links to your actual screenshots)*

| Login Page | Dashboard | Recipe Detail |
| :---: | :---: | :---: |
| ![Login Page](path/to/login_screenshot.png) | ![Dashboard](path/to/dashboard_screenshot.png) | ![Recipe Detail](path/to/recipe_detail_screenshot.png) |

---

## 🛠️ Tech Stack

-   **Backend:** Python, Django
-   **Frontend:** HTML5, CSS3, Bootstrap 5
-   **Database:** PostgreSQL
-   **Deployment:** Render
-   **Testing:** Django's built-in test framework

---

## 🗂️ Project Structure
/smart-recipe-app
│
├── core/                     # Main Django app
│   ├── migrations/
│   ├── templates/core/
│   ├── static/core/
│   ├── tests/
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   ├── forms.py
│   └── admin.py
│
├── smart_recipe/             # Project configuration folder
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
│
├── manage.py                 # Django management script
├── requirements.txt          # Dependencies
├── .env.example              # Example environment variables
└── README.md

---

## ⚙️ Getting Started

Follow these instructions to get a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

-   Python 3.8+
-   pip (Python package installer)
-   Git
-   A PostgreSQL database instance

### Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/gustavowmarques/smart-recipe-app.git](https://github.com/gustavowmarques/smart-recipe-app.git)
    cd smart-recipe-app
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    # For Mac/Linux
    python3 -m venv venv
    source venv/bin/activate

    # For Windows
    python -m venv venv
    venv\Scripts\activate
    ```

3.  **Install the dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure environment variables:**
    -   Create a `.env` file in the project root.
    -   Copy the contents of `.env.example` into your new `.env` file.
    -   Fill in the required values:
    ```ini
    DJANGO_SECRET_KEY='your-strong-secret-key'
    DEBUG=True
    ALLOWED_HOSTS=127.0.0.1,localhost
    DATABASE_URL='postgresql://USER:PASSWORD@HOST:PORT/DB_NAME'
    ```

5.  **Apply database migrations:**
    ```bash
    python manage.py migrate
    ```

6.  **Create a superuser (for admin access):**
    ```bash
    python manage.py createsuperuser
    ```

7.  **Run the development server:**
    ```bash
    python manage.py runserver
    ```
    The application will be available at `http://127.0.0.1:8000/`.

---

## ☁️ Deployment

This application is deployed on **Render**.

To deploy your own instance on Render:
1.  Fork this repository and push it to your own GitHub account.
2.  Create a new "Web Service" on Render and connect it to your forked repository.
3.  Set the build command to `pip install -r requirements.txt`.
4.  Set the start command to `gunicorn smart_recipe.wsgi`.
5.  Create a PostgreSQL database instance on Render.
6.  Add the required environment variables in the Render dashboard, ensuring `DEBUG` is set to `False` and using the `DATABASE_URL` provided by your Render database.

---

## 🧪 Running Tests

To run the automated tests for the application, execute the following command:
```bash
python manage.py test
Tests are located in the core/tests/ directory and cover models, views, and user authentication flows.

🛡️ Security Highlights
User Authentication: Secure login and registration using Django's robust auth system.

Data Protection: Password hashing and CSRF protection are enabled by default.

Permissions: Logic is in place to ensure users can only modify their own content.

Production Settings: DEBUG is set to False in the production environment to prevent exposure of sensitive information.

📅 Roadmap / Future Enhancements
[ ] Nutrition API: Integrate an API to fetch and display nutritional information for recipes.

[ ] User Profiles: Create public user profile pages with avatars and recipe collections.

[ ] Search & Filter: Implement advanced search and filtering capabilities by ingredients, tags, or cooking time.

[ ] Ratings & Favorites: Allow users to rate recipes and save their favorites.

[ ] Dockerization: Containerize the application with Docker for improved portability and easier deployment.

✨ Credits
This project was developed by Gustavo Welds Marques da Silva.
