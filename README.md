# SMS Mini Project

A FastAPI-based SMS gateway application that integrates with the **Nalo SMS API** to send SMS messages, manage delivery reports, and receive delivery status callbacks.

**Live Application:** https://sms-mini-project.onrender.com

---

## Features

- Send SMS messages using the Nalo SMS API.
- Accept recipient phone numbers and message content.
- Support configured sender IDs.
- Store SMS records in PostgreSQL.
- Receive delivery reports through HTTP callbacks.
- Manage application configuration using environment variables.
- Run locally or using Docker Compose.
- API documentation available through FastAPI Swagger UI.

## Tech Stack

- **Backend:** Python, FastAPI
- **SMS Gateway:** Nalo SMS API
- **Database:** PostgreSQL
- **Containerization:** Docker and Docker Compose
- **Deployment:** Render
- **API Documentation:** Swagger UI

## Project Structure

```text
SMS-Mini-Project/
│
├── app/
│   ├── main.py
│   ├── models/
│   ├── schemas/
│   ├── services/
│   ├── database/
│   ├── views/
│   ├── templates/
│   └── static/
│
├── .github/
│   └── workflows/
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Prerequisites

Before running the application, install:

- Python 3.12 or a compatible project version.
- Docker.
- Docker Compose.
- Git.

You will also need Nalo SMS API credentials to send real SMS messages.

## Environment Variables

Create a `.env` file in the project root.

The following environment variables configure the application:

| Variable | Description |
|---|---|
| `SMS_API_KEY` | API authentication key provided by Nalo for accessing its SMS service. |
| `NALO_API_URL` | Base URL or endpoint of the Nalo SMS API used to send messages. |
| `SENDER_IDS` | Comma-separated list of approved sender IDs that can be used when sending SMS messages. |
| `CALLBACK_BASE_URL` | Public base URL that Nalo can use to send delivery status callbacks to the application. |
| `DATABASE_URL` | Database connection string used by the application to connect to PostgreSQL or another configured database. |

### Example `.env` Configuration

```env
SMS_API_KEY=your_nalo_api_key

NALO_API_URL=your_nalo_api_endpoint

SENDER_IDS=YourSenderID

CALLBACK_BASE_URL=http://127.0.0.1:8000

DATABASE_URL=postgresql://username:password@localhost:5432/sms_db
```

Replace the example values with your actual configuration.

**Important:** Never commit your `.env` file or expose your API credentials on GitHub.

For deployment, configure the environment variables through your hosting provider's environment settings.

## Running the Application with Docker

Docker Compose allows you to run the application and its database together.

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/SMS-Mini-Project.git
```

Navigate into the project:

```bash
cd SMS-Mini-Project
```

### 2. Configure environment variables

Create your `.env` file:

```bash
cp .env.example .env
```

Update the values with your actual credentials and database configuration.

### 3. Build and start the containers

```bash
docker compose up --build
```

This builds the application image and starts the services defined in `docker-compose.yml`.

### 4. Run in the background

```bash
docker compose up --build -d
```

### 5. View application logs

```bash
docker compose logs -f
```

### 6. Stop the application

```bash
docker compose down
```

To stop the containers and remove their associated volumes:

```bash
docker compose down -v
```

**Warning:** The `-v` option removes Docker-managed volumes and may permanently delete stored database data.

## Running Locally Without Docker

You can also run the application directly using Python.

### 1. Create a virtual environment

```bash
python3 -m venv .venv
```

### 2. Activate the environment

Linux/macOS:

```bash
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create and configure your `.env` file.

Ensure your database is running and accessible.

### 5. Start the FastAPI application

```bash
uvicorn app.main:app --reload
```

The application should be available at:

```text
http://127.0.0.1:8000
```

### 6. Access API documentation

FastAPI automatically provides interactive API documentation:

```text
http://127.0.0.1:8000/docs
```

## Testing SMS Delivery Callbacks Locally

Delivery callbacks allow the Nalo SMS gateway to notify your application when an SMS changes delivery status.

Because your local development server is not publicly accessible, you need a tunneling service such as **ngrok**.

### 1. Start your application

```bash
uvicorn app.main:app --reload
```

Your application should be running at:

```text
http://127.0.0.1:8000
```

### 2. Start ngrok

In another terminal, run:

```bash
ngrok http 8000
```

ngrok will generate a public HTTPS URL, for example:

```text
https://example.ngrok-free.app
```

### 3. Configure the callback URL

Your callback URL should combine the ngrok URL with your application's callback route.

The proposed callback route is:

```text
POST /callbacks/nalo
```

Example:

```text
https://example.ngrok-free.app/callbacks/nalo
```

Set the environment variable:

```env
CALLBACK_BASE_URL=https://example.ngrok-free.app
```

Use the exact callback path and URL format expected by your implementation and Nalo's callback configuration.

### 4. Test the callback endpoint

Once the callback route is implemented, you can send a test request using curl:

```bash
curl -X POST \
  https://example.ngrok-free.app/callbacks/nalo \
  -H "Content-Type: application/json" \
  -d '{
    "status": "DELIVERED",
    "message_id": "test-message-001"
  }'
```

The JSON above is an illustrative test payload. Replace its fields with the actual payload expected by your callback handler.

### 5. Inspect the logs

Check the terminal where FastAPI is running.

You should be able to see the incoming HTTP request and the callback processing result.

You can also inspect the response returned by your application in the curl output.

**Note:** Successful local callback testing does not automatically mean Nalo is sending real delivery reports. Configure the public callback URL with Nalo and use a real SMS delivery to verify the complete integration.

## Live Deployment

The application is deployed on Render.

**Live URL:**

https://sms-mini-project.onrender.com

### API Documentation

```text
https://sms-mini-project.onrender.com/docs
```

Render manages the application deployment and provides the configured environment variables at runtime.

### Keep-Alive Automation

The repository can also use GitHub Actions to periodically send HTTP requests to the Render application.

The workflow is configured under:

```text
.github/workflows/render-keepalive.yml
```

This can help prevent inactivity-related sleeping on supported free web services, although scheduled execution delays mean it is not guaranteed.

## Security

- Never upload `.env` files to GitHub.
- Store API keys and credentials securely.
- Use GitHub Secrets for sensitive workflow configuration.
- Validate incoming delivery callback requests.
- Use HTTPS for public callback URLs.
- Avoid exposing database credentials in application logs.

## Contributing

Contributions and improvements are welcome.

1. Fork the repository.
2. Create a feature branch.
3. Make your changes.
4. Commit your changes.
5. Submit a pull request.

## License

Specify the project's license here.
