# AutoApply - Enterprise AI Job Automation Platform

AutoApply is a premium, enterprise-grade frontend application designed to automate and manage thousands of job applications. It serves as the command center for the backend ATS Automation Bot.

## Technology Stack

- **Framework**: React 19 + TypeScript
- **Bundler**: Vite
- **Styling**: TailwindCSS v4 + CSS Modules
- **State Management**: Zustand (Client) + React Query (Server)
- **Routing**: React Router v7 (Code Split & Lazy Loaded)
- **Forms & Validation**: React Hook Form + Zod
- **Animations**: Framer Motion
- **Icons**: Lucide React
- **Notifications**: Sonner

## Architecture Overview

The application is structured using a Feature-Sliced Design pattern to maintain high scalability:

```text
src/
├── api/             # Global Axios instance & interceptors
├── app/             # Application entry, global router
├── components/      # Generic, reusable UI components (Buttons, Loaders)
├── config/          # Environment variables & route constants
├── features/        # Feature modules (Search, Resume, Profile, Queue)
├── layouts/         # Global layout wrappers (DashboardLayout)
├── store/           # Global Zustand stores (Theme, User)
├── types/           # Global TypeScript interfaces
└── pages/           # High-level route components (Lazy Loaded)
```

## Environment Variables

Copy `.env.example` to `.env` and configure:

```env
VITE_API_BASE_URL=http://localhost:3000/api/v1
VITE_ENABLE_MOCK_DATA=false
```

## Development Guide

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Run TypeScript compilation check
npm run typecheck

# Run Vitest tests
npm run test
```

## Production Build Guide

The application is optimized for production out of the box using React.lazy code splitting and aggressive minification.

```bash
# Standard Build
npm run build
```

### Docker Deployment

A multi-stage `Dockerfile` is included to build the application and serve it via Nginx, optimized for Single Page Applications (SPA).

```bash
# Build the Docker image
docker build -t auto-apply-frontend .

# Run the container on port 80
docker run -p 80:80 auto-apply-frontend
```

## Contributing

1. Ensure strict TypeScript compliance (`tsc --noEmit` must pass).
2. Adhere to the established TailwindCSS styling conventions.
3. Place feature-specific business logic inside `src/features/`.
