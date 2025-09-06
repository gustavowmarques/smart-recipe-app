# Smart Recipe

Smart Recipe helps you turn your pantry into meals. Add ingredients, generate recipes with AI or search the web, and save favorites to revisit later.

## Demo flow (60–90s)
1. Register & login.
2. Add 2–4 pantry items (e.g., bell pepper, chicken breast, onion).
3. Choose **Food** (or **Drink**) → **Get AI Recipes**.
4. Open a result → **Save to Favorites**.
5. Go to **Favorites** → **View** (opens DB-backed detail, no session needed).
6. Try **Search the Web** to show matches/missing from your pantry.

## Features
- User auth (register/login/logout).
- Pantry CRUD (create/delete) with validation.
- AI recipes (OpenAI) with strict JSON and **image fallback** via Spoonacular.
- Web recipes (Spoonacular) filtered by pantry matches and dish type.
- Recipe detail pages with ingredients & instructions.
- **Favorites** (persistent DB) + session-independent favorite detail.
- Clean Bootstrap UI; mobile-friendly navbar.

## Tech
- Django 5, Python 3.13
- PostgreSQL (via `DATABASE_URL`) or SQLite locally
- OpenAI & Spoonacular APIs
- Bootstrap/Whitenoise

## Quick start

### 1) Environment
Copy the example:
```bash
cp .env.example .env
