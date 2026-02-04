<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import * as api from "./api";

type Status = "backlog" | "today" | "done";


type TaskLocal = {
  id: string;
  title: string;
  status: Status;
  createdAt: number;
  todayAt?: number;
  timeSpentSec: number;
  activeSessionStartedAt?: number;
};


const email = ref("");
const password = ref("");
const errorMsg = ref<string | null>(null);
const loading = ref(false);

const token = ref<string | null>(localStorage.getItem("token"));
const isAuthed = computed(() => !!token.value);

function saveToken(t: string) {
  localStorage.setItem("token", t);
  token.value = t;
}

async function logout() {
  await stopAll(); 
  localStorage.removeItem("token");
  token.value = null;
  tasks.value = [];
}


function formatTime(sec: number) {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;

  const hh = h > 0 ? `${h}ч ` : "";
  const mm = h > 0 || m > 0 ? `${m}м ` : "";
  return `${hh}${mm}${s}с`.trim();
}

function fromServer(t: api.Task): TaskLocal {
  return {
    id: t.id,
    title: t.title,
    status: t.status,
    createdAt: t.createdAt,
    todayAt: t.todayAt ?? undefined,
    timeSpentSec: t.timeSpentSec,
  };
}


const tasks = ref<TaskLocal[]>([]);
const newTitle = ref("");

const backlog = computed(() =>
  tasks.value
    .filter(t => t.status === "backlog")
    .sort((a, b) => b.createdAt - a.createdAt)
);

const today = computed(() =>
  tasks.value
    .filter(t => t.status === "today")
    .sort((a, b) => (a.todayAt ?? 0) - (b.todayAt ?? 0))
);

const done = computed(() =>
  tasks.value
    .filter(t => t.status === "done")
    .sort((a, b) => b.createdAt - a.createdAt)
);

const activeTaskId = computed(() => tasks.value.find(t => t.activeSessionStartedAt)?.id ?? null);

function getTask(id: string) {
  return tasks.value.find(t => t.id === id);
}


async function syncFromServer() {
  if (!isAuthed.value) return;
  errorMsg.value = null;

  try {
    const serverTasks = await api.getTasks();
    tasks.value = serverTasks.map(fromServer);
  } catch (e: any) {
    errorMsg.value = e?.message ?? "Sync error";
  }
}

async function onRegister() {
  errorMsg.value = null;
  loading.value = true;

  try {
    const res = await api.register(email.value.trim(), password.value);
    saveToken(res.token);
    await syncFromServer();
  } catch (e: any) {
    errorMsg.value = e?.message ?? "Register error";
  } finally {
    loading.value = false;
  }
}

async function onLogin() {
  errorMsg.value = null;
  loading.value = true;

  try {
    const res = await api.login(email.value.trim(), password.value);
    saveToken(res.token);
    await syncFromServer();
  } catch (e: any) {
    errorMsg.value = e?.message ?? "Login error";
  } finally {
    loading.value = false;
  }
}


async function addTask() {
  const title = newTitle.value.trim();
  if (!title) return;

  errorMsg.value = null;
  try {
    const created = await api.createTask(title);
    tasks.value.unshift(fromServer(created));
    newTitle.value = "";
  } catch (e: any) {
    errorMsg.value = e?.message ?? "Create task error";
  }
}

function stopIfActiveLocal(t: TaskLocal) {
  if (!t.activeSessionStartedAt) return;

  const delta = Math.max(0, Math.floor((Date.now() - t.activeSessionStartedAt) / 1000));
  t.timeSpentSec += delta;
  delete t.activeSessionStartedAt;
}

async function stopIfActive(id: string) {
  const t = getTask(id);
  if (!t || !t.activeSessionStartedAt) return;

  stopIfActiveLocal(t);

  
  try {
    await api.updateTask(id, { timeSpentSec: t.timeSpentSec });
  } catch (e: any) {
    errorMsg.value = e?.message ?? "Update time error";
  }
}

async function stopAll() {
  for (const t of tasks.value) {
    if (t.activeSessionStartedAt) {
      await stopIfActive(t.id);
    }
  }
}

async function moveToToday(id: string) {
  const t = getTask(id);
  if (!t) return;

  t.status = "today";
  t.todayAt = Date.now();

  try {
    await api.updateTask(id, { status: "today", todayAt: t.todayAt });
  } catch (e: any) {
    errorMsg.value = e?.message ?? "Move to today error";
  }
}

async function moveToBacklog(id: string) {
  await stopIfActive(id);

  const t = getTask(id);
  if (!t) return;

  t.status = "backlog";
  delete t.todayAt;

  try {
    
    await api.updateTask(id, { status: "backlog" });
  } catch (e: any) {
    errorMsg.value = e?.message ?? "Move to backlog error";
  }
}

async function markDone(id: string) {
  await stopIfActive(id);

  const t = getTask(id);
  if (!t) return;

  t.status = "done";
  delete t.todayAt;

  try {
    await api.updateTask(id, { status: "done" });
  } catch (e: any) {
    errorMsg.value = e?.message ?? "Mark done error";
  }
}

async function startTask(id: string) {
  
  const current = tasks.value.find(x => x.activeSessionStartedAt);
  if (current && current.id !== id) {
    await stopIfActive(current.id);
  }

  const t = getTask(id);
  if (!t) return;

  
  if (t.status !== "today") t.status = "today";
  if (!t.todayAt) t.todayAt = Date.now();

  if (!t.activeSessionStartedAt) t.activeSessionStartedAt = Date.now();

  try {
    await api.updateTask(id, { status: "today", todayAt: t.todayAt });
  } catch (e: any) {
    errorMsg.value = e?.message ?? "Start task error";
  }
}

async function toggleTask(id: string) {
  const t = getTask(id);
  if (!t) return;

  if (t.activeSessionStartedAt) {
    await stopIfActive(id);
  } else {
    await startTask(id);
  }
}

async function deleteTask(id: string) {
  await stopIfActive(id);

  errorMsg.value = null;
  try {
    await api.deleteTask(id);
    tasks.value = tasks.value.filter(t => t.id !== id);
  } catch (e: any) {
    errorMsg.value = e?.message ?? "Delete error";
  }
}


const tick = ref(0);
let interval: number | undefined;

function displayedTime(task: TaskLocal) {
  if (!task.activeSessionStartedAt) return task.timeSpentSec;
  void tick.value;
  const extra = Math.max(0, Math.floor((Date.now() - task.activeSessionStartedAt) / 1000));
  return task.timeSpentSec + extra;
}

async function onBeforeUnload() {
  await stopAll();
}

onMounted(async () => {
  interval = window.setInterval(() => (tick.value++), 1000);
  window.addEventListener("beforeunload", onBeforeUnload);

  if (isAuthed.value) {
    await syncFromServer();
  }
});

onBeforeUnmount(async () => {
  if (interval) clearInterval(interval);
  window.removeEventListener("beforeunload", onBeforeUnload);
  await stopAll();
});
</script>

<template>
 
  <div
    v-if="!isAuthed"
    style="
      max-width: 420px;
      margin: 40px auto;
      padding: 16px;
      border: 1px solid #ddd;
      border-radius: 12px;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial;
    "
  >
    <h2 style="margin: 0 0 12px">Вход / Регистрация</h2>

    <div style="display: grid; gap: 10px">
      <input v-model="email" placeholder="Email" />
      <input v-model="password" placeholder="Password (min 6)" type="password" />

      <div style="display: flex; gap: 8px">
        <button :disabled="loading" @click="onRegister">Register</button>
        <button :disabled="loading" @click="onLogin">Login</button>
      </div>

      <p v-if="errorMsg" style="color: #c00; margin: 0">{{ errorMsg }}</p>

      
    </div>
  </div>

  
  <div v-else class="wrap">
    <header class="header">
      <div class="top">
        <h1>Todo Practice (Vue)</h1>

        <div style="display: flex; gap: 8px; align-items: center">
          <button class="ghost" @click="syncFromServer">Sync</button>
          <button class="ghost" @click="logout">Logout</button>
        </div>
      </div>

      <div class="mini">
        Активная задача:
        <b>{{ activeTaskId ? "есть" : "нет" }}</b>
      </div>

      <p v-if="errorMsg" style="color: #c00; margin: 0">{{ errorMsg }}</p>

      <form class="form" @submit.prevent="addTask">
        <input v-model="newTitle" placeholder="Новая задача..." />
        <button type="submit">Добавить</button>
      </form>
    </header>

    <main class="grid">
      
      <section class="col">
        <div class="colHead">
          <h2>Очередь</h2>
          <span class="count">{{ backlog.length }}</span>
        </div>

        <div v-if="backlog.length === 0" class="empty">Пока пусто</div>

        <article v-for="t in backlog" :key="t.id" class="card">
          <div class="title">{{ t.title }}</div>
          <div class="meta">Время: {{ formatTime(displayedTime(t)) }}</div>
          <div class="actions">
            <button @click="moveToToday(t.id)">На сегодня</button>
            <button class="ghost" @click="deleteTask(t.id)">Удалить</button>
          </div>
        </article>
      </section>

     
      <section class="col">
        <div class="colHead">
          <h2>Сегодня</h2>
          <span class="count">{{ today.length }}</span>
        </div>

        <div v-if="today.length === 0" class="empty">Нет задач на сегодня</div>

        <article
          v-for="t in today"
          :key="t.id"
          class="card"
          :class="{ active: !!t.activeSessionStartedAt }"
        >
          <div class="titleRow">
            <div class="title">{{ t.title }}</div>
            <span v-if="t.activeSessionStartedAt" class="badge">ACTIVE</span>
          </div>

          <div class="meta">Время: {{ formatTime(displayedTime(t)) }}</div>

          <div class="actions">
            <button @click="toggleTask(t.id)">
              {{ t.activeSessionStartedAt ? "Стоп" : "Старт" }}
            </button>
            <button @click="markDone(t.id)">Выполнено</button>
            <button class="ghost" @click="moveToBacklog(t.id)">В очередь</button>
          </div>
        </article>
      </section>

     
      <section class="col">
        <div class="colHead">
          <h2>Выполнено</h2>
          <span class="count">{{ done.length }}</span>
        </div>

        <div v-if="done.length === 0" class="empty">Ещё ничего не сделано</div>

        <article v-for="t in done" :key="t.id" class="card done">
          <div class="title">{{ t.title }}</div>
          <div class="meta">Итого: {{ formatTime(displayedTime(t)) }}</div>
          <div class="actions">
            <button class="ghost" @click="deleteTask(t.id)">Удалить</button>
          </div>
        </article>
      </section>
    </main>

    
  </div>
</template>

<style scoped>
.wrap { max-width: 1100px; margin: 0 auto; padding: 22px; }
.header { display: grid; gap: 12px; margin-bottom: 14px; }
.top { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
h1 { margin: 0; font-size: 22px; }
.mini { color: #555; font-size: 13px; }

.form { display: flex; gap: 10px; }
input {
  flex: 1;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 12px;
  outline: none;
  background: white;
}
button {
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 12px;
  background: white;
  cursor: pointer;
}
button:hover { border-color: #bbb; }
button.ghost { background: transparent; }

.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.col {
  border: 1px solid #eaeaea;
  border-radius: 16px;
  padding: 12px;
  background: #fafafa;
  min-height: 320px;
}
.colHead { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
h2 { margin: 0; font-size: 16px; }
.count {
  font-size: 12px;
  padding: 2px 9px;
  border: 1px solid #ddd;
  border-radius: 999px;
  color: #555;
  background: white;
}

.card {
  border: 1px solid #e9e9e9;
  border-radius: 16px;
  padding: 10px;
  background: white;
  display: grid;
  gap: 8px;
  margin-bottom: 10px;
}
.card.active {
  border-color: #cfcfcf;
  box-shadow: 0 1px 12px rgba(0,0,0,0.06);
}
.card.done { opacity: 0.86; }

.title { font-weight: 650; }
.titleRow { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.badge {
  font-size: 11px;
  padding: 2px 8px;
  border: 1px solid #ddd;
  border-radius: 999px;
  background: #fff;
}

.meta { font-size: 13px; color: #555; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
.empty { color: #777; font-size: 13px; padding: 10px 2px; }

.footer { margin-top: 12px; color: #666; font-size: 12px; }

@media (max-width: 980px) {
  .grid { grid-template-columns: 1fr; }
}
</style>
