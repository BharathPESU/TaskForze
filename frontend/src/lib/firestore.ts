/**
 * Firestore helpers — per-user collections.
 *
 * Data lives under:
 *   users/{uid}/tasks
 *   users/{uid}/workflows
 *   users/{uid}/messages
 */
import {
  addDoc,
  collection,
  deleteDoc,
  doc,
  getDocs,
  limit,
  onSnapshot,
  orderBy,
  query,
  serverTimestamp,
  setDoc,
  type Unsubscribe,
} from "firebase/firestore";

import { db } from "./firebase";
import type { TaskItem, WorkflowItem } from "./nexus";

// ─── Collection refs ──────────────────────────────────────────────────────────

function tasksCol(uid: string) {
  return collection(db, "users", uid, "tasks");
}

function workflowsCol(uid: string) {
  return collection(db, "users", uid, "workflows");
}

function messagesCol(uid: string) {
  return collection(db, "users", uid, "messages");
}

// ─── Tasks ───────────────────────────────────────────────────────────────────

export async function saveTask(uid: string, task: TaskItem) {
  const ref = doc(tasksCol(uid), task.id);
  await setDoc(ref, { ...task, syncedAt: serverTimestamp() }, { merge: true });
}

export async function syncTasks(uid: string, tasks: TaskItem[]) {
  await Promise.allSettled(tasks.map((t) => saveTask(uid, t)));
}

export function subscribeToTasks(
  uid: string,
  onUpdate: (tasks: TaskItem[]) => void
): Unsubscribe {
  const q = query(tasksCol(uid), orderBy("syncedAt", "desc"), limit(50));
  return onSnapshot(q, (snap) => {
    onUpdate(snap.docs.map((d) => d.data() as TaskItem));
  });
}

// ─── Workflows ───────────────────────────────────────────────────────────────

export async function saveWorkflow(uid: string, workflow: WorkflowItem) {
  const ref = doc(workflowsCol(uid), workflow.id);
  await setDoc(
    ref,
    { ...workflow, syncedAt: serverTimestamp() },
    { merge: true }
  );
}

export async function syncWorkflows(uid: string, workflows: WorkflowItem[]) {
  await Promise.allSettled(workflows.map((w) => saveWorkflow(uid, w)));
}

export function subscribeToWorkflows(
  uid: string,
  onUpdate: (workflows: WorkflowItem[]) => void
): Unsubscribe {
  const q = query(
    workflowsCol(uid),
    orderBy("syncedAt", "desc"),
    limit(20)
  );
  return onSnapshot(q, (snap) => {
    onUpdate(snap.docs.map((d) => d.data() as WorkflowItem));
  });
}

// ─── Messages ────────────────────────────────────────────────────────────────

export type StoredMessage = {
  id?: string;
  role: "user" | "assistant";
  content: string;
  createdAt?: unknown;
};

export async function appendMessage(
  uid: string,
  message: Omit<StoredMessage, "id">
) {
  await addDoc(messagesCol(uid), {
    ...message,
    createdAt: serverTimestamp(),
  });
}

export async function getRecentMessages(
  uid: string
): Promise<StoredMessage[]> {
  const q = query(messagesCol(uid), orderBy("createdAt", "asc"), limit(50));
  const snap = await getDocs(q);
  return snap.docs.map((d) => ({ id: d.id, ...d.data() } as StoredMessage));
}
