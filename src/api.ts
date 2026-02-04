const API_BASE = "http://127.0.0.1:8000";



export type AuthResponse = {
  token: string;
  user: {
    id: string;
    email: string;
  };
};

export type TaskStatus = "backlog" | "today" | "done";

export type Task = {
  id: string;
  title: string;
  status: TaskStatus;
  createdAt: number;
  todayAt: number | null;
  timeSpentSec: number;
  updatedAt: number;
};



function getToken(): string | null {
  return localStorage.getItem("token");
}

function authHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}



async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(options.headers as HeadersInit),
  };

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${text}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}



export async function register(
  email: string,
  password: string
): Promise<AuthResponse> {
  return request<AuthResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function login(
  email: string,
  password: string
): Promise<AuthResponse> {
  return request<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}



export async function getTasks(): Promise<Task[]> {
  return request<Task[]>("/tasks", {
    method: "GET",
    headers: authHeaders(),
  });
}

export async function createTask(title: string): Promise<Task> {
  return request<Task>("/tasks", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({
      title,
      status: "backlog",
      timeSpentSec: 0,
    }),
  });
}

export async function updateTask(
  taskId: string,
  patch: Partial<
    Pick<Task, "title" | "status" | "todayAt" | "timeSpentSec">
  >
): Promise<Task> {
  return request<Task>(`/tasks/${taskId}`, {
    method: "PUT",
    headers: authHeaders(),
    body: JSON.stringify(patch),
  });
}

export async function deleteTask(taskId: string): Promise<void> {
  return request<void>(`/tasks/${taskId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
}

