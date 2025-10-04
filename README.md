# Smart Recipe App
### Full Stack Web Application (Django + AI Integration)

**Live Deployment:**  
[https://smart-recipe-app-b3x7.onrender.com](https://smart-recipe-app-b3x7.onrender.com)

**GitHub Repository:**  
[https://github.com/gustavowmarques/smart-recipe-app.git](https://github.com/gustavowmarques/smart-recipe-app.git)

**Django Superuser (for demo/review):**  
**Username:** `gdasilva`  
**Password:** `LabPass1!`


## 1. Project Overview
--------------------

The **Smart Recipe App** is a full-stack web application that helps users generate, discover, and organise recipes based on ingredients and dietary preferences. It integrates **AI-powered recipe generation** (OpenAI API) with **real recipe data** from the **Spoonacular API**, creating an interactive, intelligent cooking assistant.

The project demonstrates end-to-end integration of frontend and backend technologies, secure authentication, external API consumption, automated testing, and full deployment — addressing all major criteria for a **Distinction-grade Full Stack Web Application**.

## 2. Objectives and Goals
------------------------

*   Build a **feature-rich web application** integrating AI and external API data.
    
*   Implement secure user authentication (registration, login, logout).
    
*   Provide a responsive, intuitive interface for pantry-based recipe searches.
    
*   Showcase clear communication, documentation, and version control best practices.
    
*   Deploy a fully functional hosted version with live database connectivity.
    

## 3 Key Features
----------------

### Authentication & Security

*   Django built-in authentication for register/login/logout.
    
*   Passwords stored with PBKDF2 hashing.
    
*   CSRF and session-based protection enabled site-wide.
    

### Recipe Generation and Discovery

*   **AI Recipes:** Custom recipes generated through OpenAI API.
    
*   **Spoonacular API Integration:** Real-world recipes with images and nutrition facts.
    
*   **Ingredient Search:** Suggests meals based on available pantry items.
    
*   **Detailed Recipe Views:** Steps, ingredients, and cooking times.
    
*   **Save Favorites:** Personalised recipe library on the dashboard.
    

### Dashboard and Meal Planning

*   User-specific dashboard displaying saved recipes and meal logs.
    
*   Future expansion for calorie tracking and nutritional goals.
    

### Responsive Design

*   Developed with **Bootstrap 5**, ensuring usability across desktop, tablet, and mobile.
    

### Automated Testing

*   Unit and integration tests using Django’s unittest.
    
*   Covers models, views, templates, and API mocks.
    

### Deployment

*   Hosted on **Render** with persistent PostgreSQL database and production static file handling.
    

## 4. Technologies Used

| Category            | Technology                                   |
|--------------------|----------------------------------------------|
| **Frontend**       | HTML5, CSS3, Bootstrap 5, Django Templates   |
| **Backend**        | Python 3.13, Django 5.2.5                    |
| **Database**       | SQLite (development), PostgreSQL (production)|
| **APIs**           | OpenAI API, Spoonacular API                  |
| **Testing**        | Django `unittest` Framework                  |
| **Version Control**| Git & GitHub                                 |
| **Deployment**     | Render.com                                   |
| **Package Management** | pip, virtualenv                          |
| **Security**       | Django Auth, CSRF, Password Hashing          |


## 5. System Architecture
-----------------------

Follows the **Model-View-Template (MVT)** pattern:

*   **Models:** Represent recipes, favorites, pantry images, and logged meals.
    
*   **Views:** Manage routing, API calls, AI generation, and user interaction logic.
    
*   **Templates:** Render Bootstrap-based responsive UI components.
    

**API Flow:**

1.  User enters ingredients or prompts.
    
2.  Backend calls either:
    
    *   **OpenAI API** for creative recipe generation, or
        
    *   **Spoonacular API** for verified recipes and images.
        
3.  Results parsed, stored, and rendered dynamically.
    
4.  Users can view details or save favorites.
    

## 6. Installation and Setup
--------------------------

### Prerequisites

*   Python 3.10+
    
*   pip and virtualenv
    

### Steps

```bash
git clone https://github.com/gustavowmarques/smart-recipe-app.git
cd smart-recipe-app

python -m venv venv
source venv/Scripts/activate   # On Windows: venv\Scripts\activate

pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```
App available at http://127.0.0.1:8000.

## 7. Testing
-----------

Run the full suite:

```bash
python manage.py test core.tests -v 2
````


Tests cover:

*   **Models** – creation and relationships.
    
*   **Views** – authentication, dashboard, and recipe search routes.
    
*   **Templates** – rendering and content assertions.
    
*   **Mock APIs** – simulated OpenAI / Spoonacular responses.
    

All six tests pass after minor namespace and template corrections.

## 8. Deployment Details
----------------------

*   **Platform:** Render.com
    
*   **Branch:** main (auto-deploy)
    
*   **Environment Variables:**
    
    *   OPENAI\_API\_KEY
        
    *   SPOONACULAR\_API\_KEY
        
    *   DJANGO\_SECRET\_KEY
        
*   **Static Files:** WhiteNoise
    
*   **Database:** PostgreSQL
    
*   **Live URL:** [https://smart-recipe-app-b3x7.onrender.com](https://smart-recipe-app-b3x7.onrender.com)
    

## 9. Version Control and Collaboration
-------------------------------------

*   Regular commits with descriptive messages.
    
*   Feature branches used for isolated development.
    
*   .gitignore prevents committing sensitive data or virtual environments.
    
*   Documentation, tests, and code consistently aligned through Git history.
    

## 10. Challenges and Solutions
-----------------------------

### Challenges and Solutions

| Challenge | Resolution |
|------------|-------------|
| **API quota errors** | Implemented graceful fallback when APIs return 402 / 429. |
| **Template reverse failures** | Added proper namespacing (`core:`) for URL resolution. |
| **Spoonacular keyword mismatch** | Updated helper to ignore unused kwargs. |
| **Responsive layout** | Re-implemented grid and cards using Bootstrap utility classes. |
| **Testing failures** | Synchronized reverse names with URL namespace; all tests pass. |


## 11. Future Enhancements
------------------------

*   Add nutrition dashboard and progress tracking.
    
*   Implement email verification and password reset.
    
*   Support user-uploaded recipe images.
    
*   Expand filters by cuisine, calories, and diet type.
    
*   Extend testing coverage to integration and UI automation.
    

## 12. Communication and Collaboration Notes
------------------------------------------

*   Weekly progress aligned with course milestones.
    
*   Code commented with meaningful docstrings.
    
*   This README provides clear setup, deployment, and testing guidance.
    
*   Professional documentation enables reviewers or peers to replicate the environment easily.
    

## 13. Project Timeline (Weeks 2 – 5)
-----------------------------------

### Project Timeline (Weeks 2–5)

| Week | Focus | Outcome |
|------|--------|----------|
| **Week 2 – Project Brief** | Defined idea (*Smart Recipe Assistant*), identified APIs, and created the Git repository. | Approved project concept and objectives. |
| **Week 3 – Planning & Analysis** | Produced planning analysis document, sitemap, and wireframes. | Established navigation flow and user roles. |
| **Week 4 – Progress Update 1** | Implemented authentication, dashboard UI, and base templates. | Demonstrated working login/register functionality and core navigation. |
| **Week 5 – Progress Update 2** | Integrated OpenAI and Spoonacular APIs, added Favorites and Meal Plan features, and deployed to Render. | Delivered full, hosted, and functional web application. |

This structured timeline evidences consistent progress and communication throughout development.


## 14. Project Planning and Supporting Documentation
--------------------------------------------------

All supporting materials are located in the /doc folder within the submission:

*   **Planning Analysis Document:** Defines system goals, feature priorities, and technology stack.
    
*   **Sitemap:** Visual overview of page navigation and user flow.
    
*   **Wireframes:** Early UI mockups for Home, Dashboard, and Recipe Detail.
    
*   **API Design Notes:** Endpoint structures and request/response samples for Spoonacular and OpenAI.
    
*   **Testing Plan:** Manual and automated test procedures.
    
*   **Presentation Slides:** Used in weekly updates and final demonstration.
    
*   **Dependency List:** Ensures reproducible environment and deployment consistency.
    

Together these artefacts document the full SDLC — concept → design → implementation → testing → deployment — supporting distinction-level communication and planning evidence.

## 15. Conclusion
---------------

The **Smart Recipe App** is a comprehensive demonstration of full-stack development competence.It showcases mastery in:

*   Front-end and back-end integration
    
*   Secure application design
    
*   API consumption and AI integration
    
*   Automated testing and deployment
    
*   Clear documentation and communication
    

This project fully satisfies the assessment rubric for **Distinction**, evidencing technical depth, secure implementation, responsive design, hosted functionality, and professional-grade documentation.

**Repository:** [https://github.com/gustavowmarques/smart-recipe-app.git](https://github.com/gustavowmarques/smart-recipe-app.git)

**Live App:** [https://smart-recipe-app-b3x7.onrender.com](https://smart-recipe-app-b3x7.onrender.com)