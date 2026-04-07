"use client";

import { startTransition, useEffect, useRef, useState } from "react";
import { signOut } from "firebase/auth";
import { motion, AnimatePresence } from "framer-motion";
import Image from "next/image";
import {
  Activity,
  Bell,
  Bot,
  Calendar,
  CheckCircle2,
  Clock,
  Clock3,
  Hexagon,
  Layout,
  LogOut,
  Menu,
  MessageCircle,
  Mic,
  Play,
  Send,
  CloudUpload,
  Settings,
  ShieldAlert,
  Sparkles,
  Smartphone,
  Cpu,
  Terminal,
  PhoneCall,
  Link2,
  Star,
  MessageSquare,
  Search,
  ChevronDown,
  Plus,
  HardDrive,
  Users,
  Palette,
  PenBox,
  Check,
  Mail,
} from "lucide-react";

import { AuthGuard } from "@/components/AuthGuard";
import { useAuth } from "@/components/AuthProvider";
import { auth } from "@/lib/firebase";
import {
  apiPath,
  nexusFetch,
  type AgentStatus,
  type AuthStatus,
  type ResultEvent,
  type TaskItem,
  type TraceEvent,
  type WorkflowItem,
} from "@/lib/nexus";
import { saveTask, saveWorkflow, syncTasks, syncWorkflows } from "@/lib/firestore";
import { AlertCircle, ExternalLink } from "lucide-react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type Message = {
  role: "user" | "assistant";
  content: string;
};

const EMPTY_AGENTS: AgentStatus[] = [
  { name: "orchestrator", status: "idle", message: "Ready to coordinate", type: "primary" },
  { name: "calendar", status: "idle", message: "Watching time", type: "assistant" },
  { name: "task", status: "idle", message: "Organizing work", type: "assistant" },
  { name: "notes", status: "idle", message: "Holding context", type: "assistant" },
  { name: "comms", status: "idle", message: "Ready to draft", type: "assistant" },
  { name: "reminder", status: "idle", message: "Monitoring deadlines", type: "background" },
];

function formatDate(value?: string | number | Date | null) {
  if (!value) return "No deadline";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function prettifyName(name: string) {
  return name.split("_").map((p) => p.charAt(0).toUpperCase() + p.slice(1)).join(" ");
}

function parseEventBlock(block: string) {
  if (!block.trim()) return null;
  const lines = block.split("\n");
  let eventType = "message";
  let data = "";
  for (const line of lines) {
    if (line.startsWith("event:")) eventType = line.slice(6).trim();
    if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return null;
  try {
    return { eventType, payload: JSON.parse(data) as Record<string, unknown> };
  } catch {
    return null;
  }
}

function replaceLastAssistantMessage(messages: Message[], content: string) {
  const next = [...messages];
  for (let idx = next.length - 1; idx >= 0; idx -= 1) {
    if (next[idx]?.role === "assistant") {
      next[idx] = { role: "assistant", content };
      return next;
    }
  }
  next.push({ role: "assistant", content });
  return next;
}

function formatResultMessage(result: ResultEvent) {
  const sections = [result.summary];
  if (result.key_actions?.length) sections.push(`Actions taken: ${result.key_actions.join(", ")}`);
  if (result.follow_up_suggestions?.length) sections.push(`You might also want to: ${result.follow_up_suggestions.join(" | ")}`);
  return sections.join("\n\n");
}

export default function Dashboard() {
  const { user } = useAuth();
  
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [trace, setTrace] = useState<TraceEvent[]>([]);
  const [agents, setAgents] = useState<AgentStatus[]>(EMPTY_AGENTS);
  
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowItem[]>([]);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [backendOnline, setBackendOnline] = useState(true);
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [authFlash, setAuthFlash] = useState<{ type: "success" | "error", message: string } | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [activeTab, setActiveTab] = useState<"chat" | "tasks" | "calendar" | "connection">("chat");

  const [isRecording, setIsRecording] = useState(false);
  const [recordingTranscript, setRecordingTranscript] = useState("");
  const recognitionRef = useRef<any>(null);
  const [searchQuery, setSearchQuery] = useState("");

  const connectors = [
    { id: "gdrive", name: "Google Drive", desc: "Access, sync, and manage files securely on Google Drive.", icon: <HardDrive className="text-blue-400 h-4 w-4" /> },
    { id: "mail", name: "Mail", desc: "Send, receive, and analyze emails using intelligent parsing.", icon: <Mail className="text-red-400 h-4 w-4" /> },
    { id: "phone", name: "Phone", desc: "Initiate smart AI phone calls and automate voice interactions.", icon: <PhoneCall className="text-emerald-400 h-4 w-4" /> },
    { id: "contacts", name: "Contacts", desc: "Sync and manage your address book and professional network.", icon: <Users className="text-orange-400 h-4 w-4" /> },
    { id: "canva", name: "Canva", desc: "Generate graphics, presentations, and manage design templates.", icon: <Palette className="text-cyan-400 h-4 w-4" /> },
    { id: "word", name: "Word Editor", desc: "Rich text editor integration to draft and format documents.", icon: <PenBox className="text-blue-500 h-4 w-4" /> },
    { id: "alarm", name: "Alarm", desc: "Set sophisticated alarms, timers, and scheduled event triggers.", icon: <Bell className="text-yellow-400 h-4 w-4" /> },
    { id: "whatsapp", name: "WhatsApp", desc: "Connect automated conversation workflows via WhatsApp.", icon: <MessageCircle className="text-green-400 h-4 w-4" /> },
    { id: "agent", name: "AI Agent", desc: "Deploy specialized autonomous sub-agents to handle tasks.", icon: <Bot className="text-purple-400 h-4 w-4" /> },
  ];

  const messagesEndRef = useRef<HTMLDivElement>(null);

  async function pollBackendState() {
    try {
      const [{ agents: pulledAgents }, pulledTasks, pulledWorkflows, pulledAuth] = await Promise.all([
        nexusFetch<{ agents: AgentStatus[] }>("/agents/status"),
        nexusFetch<TaskItem[]>("/tasks"),
        nexusFetch<WorkflowItem[]>("/workflows"),
        nexusFetch<AuthStatus>("/auth/status"),
      ]);
      
      startTransition(() => {
        setBackendOnline(true);
        setConnectionError(null);
        setAuthStatus(pulledAuth);
        
        if (pulledAgents) {
          const incoming = new Map(pulledAgents.map((a) => [a.name, a]));
          setAgents(EMPTY_AGENTS.map((a) => ({ ...a, ...(incoming.get(a.name) ?? {}) })));
        }
        
        if (Array.isArray(pulledTasks)) {
          setTasks(pulledTasks);
          if (user?.uid) void syncTasks(user.uid, pulledTasks);
        }
        
        if (Array.isArray(pulledWorkflows)) {
          setWorkflows(pulledWorkflows);
          if (user?.uid) void syncWorkflows(user.uid, pulledWorkflows);
        }
      });
    } catch (err) {
      setBackendOnline(false);
    }
  }

  function handleStreamEvent(eventType: string, payload: Record<string, unknown>) {
    if (eventType === "trace") {
      const event = payload as unknown as TraceEvent;
      startTransition(() => {
        setTrace((c) => [event, ...c].slice(0, 18));
        setAgents((c) =>
          c.map((a) =>
            a.name === event.agent ? { ...a, status: event.status || "active", message: event.message } : a
          )
        );
        setMessages((c) => replaceLastAssistantMessage(c, `[${prettifyName(event.agent)}] ${event.message}`));
      });
      return;
    }
    if (eventType === "result") {
      const result = payload as unknown as ResultEvent;
      startTransition(() => {
        setAgents((c) =>
          c.map((a) => {
            const output = result.workflow?.agent_outputs?.[a.name];
            return output ? { ...a, status: output.status === "error" ? "error" : "done", message: output.summary ?? output.error ?? a.message } : a;
          })
        );
        setMessages((c) => replaceLastAssistantMessage(c, formatResultMessage(result)));
      });
    }
  }

  useEffect(() => {
    if (user?.uid) {
      void pollBackendState();
      const interval = window.setInterval(pollBackendState, 5000);
      return () => window.clearInterval(interval);
    }
  }, [user?.uid]);

  useEffect(() => {
    // Check URL for auth callbacks
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      const authQuery = url.searchParams.get("auth");
      const msgQuery = url.searchParams.get("message");
      if (authQuery) {
        if (authQuery === "success") {
          setAuthFlash({ type: "success", message: "Google Workspace connected successfully!" });
        } else if (authQuery === "error") {
          setAuthFlash({ type: "error", message: `Connection failed. ${msgQuery || ""}` });
        } else if (authQuery === "needs_setup") {
          setAuthFlash({ type: "error", message: "Missing GOOGLE_OAUTH_CLIENT_ID / SECRET in backend env!" });
        }

        // Clean up URL
        url.searchParams.delete("auth");
        url.searchParams.delete("message");
        window.history.replaceState({}, document.title, url.toString());

        // Auto dismiss flash
        setTimeout(() => setAuthFlash(null), 8000);
      }
    }
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, trace]);

  async function sendChatMessage(text: string) {
    if (!text || isLoading) return;

    setTrace([]);
    setIsLoading(true);
    setMessages((c) => [
      ...c,
      { role: "user", content: text },
      { role: "assistant", content: "Thinking..." },
    ]);

    try {
      const response = await fetch(apiPath("/chat"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({ message: text, user_id: user?.uid || "guest", stream: true }),
      });

      if (!response.ok || !response.body) throw new Error("Connection failed");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() ?? "";
        for (const block of blocks) {
          const parsed = parseEventBlock(block);
          if (parsed) handleStreamEvent(parsed.eventType, parsed.payload);
        }
      }
      if (buffer.trim()) {
        const parsed = parseEventBlock(buffer);
        if (parsed) handleStreamEvent(parsed.eventType, parsed.payload);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Error";
      setConnectionError(`Could not reach TaskForze: ${msg}`);
      setMessages((c) => replaceLastAssistantMessage(c, `I couldn't process that right now. Please try again.`));
    } finally {
      setIsLoading(false);
      void pollBackendState();
    }
  }

  async function handleSubmit() {
    const text = input.trim();
    if (!text) return;
    setInput("");
    await sendChatMessage(text);
  }

  function toggleRecording() {
    if (isRecording) {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
      setIsRecording(false);
      return;
    }

    try {
      // @ts-ignore
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SpeechRecognition) {
        alert("Speech Recognition API is not supported in this browser.");
        return;
      }
      
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      
      let fullTranscript = "";
      
      recognition.onstart = () => {
        setIsRecording(true);
        setRecordingTranscript("");
      };
      
      recognition.onresult = (event: any) => {
        let currentString = "";
        for (let i = 0; i < event.results.length; ++i) {
          currentString += event.results[i][0].transcript;
        }
        fullTranscript = currentString;
        setRecordingTranscript(currentString);
      };
      
      recognition.onerror = (event: any) => {
        console.error("Speech recognition error", event.error);
        setIsRecording(false);
      };
      
      recognition.onend = () => {
        setIsRecording(false);
        setRecordingTranscript("");
        if (fullTranscript.trim()) {
          const finalPrompt = "I am sending you an audio transcript of my surroundings. Please analyze this and create a comprehensive note from it:\n\n" + fullTranscript.trim();
          sendChatMessage(finalPrompt);
        }
      };
      
      recognitionRef.current = recognition;
      recognition.start();
    } catch (e) {
      console.error(e);
      alert("Failed to start speech recognition.");
    }
  }

  const handleSignOut = () => void signOut(auth);
  const liveAgents = agents.filter((a) => a.status !== "idle").length;

  return (
    <AuthGuard>
      <div className="flex h-screen w-full text-[#e2e8f0] bg-transparent">
        
        {/* SIDEBAR */}
        <aside className="hidden flex-col items-center border-r border-white/10 bg-black/40 backdrop-blur-xl py-6 md:flex md:w-20 shrink-0 z-10">
          <div className="mb-8 rounded-xl bg-gradient-to-tr from-[#7b61ff] to-[#4c2dff] p-2.5 shadow-[0_0_15px_rgba(123,97,255,0.3)]">
            <Layout className="h-6 w-6 text-white" />
          </div>
          
          <nav className="flex w-full flex-1 flex-col items-center gap-6">
            <button
              onClick={() => setActiveTab("chat")}
              className={`flex h-12 w-12 items-center justify-center rounded-2xl border transition-all ${
                activeTab === "chat"
                  ? "border-[#7b61ff]/50 bg-[#7b61ff]/20 text-[#7b61ff] shadow-[0_0_15px_rgba(123,97,255,0.3)] scale-105"
                  : "border-transparent text-[#94a3b8] hover:bg-white/5 hover:text-white"
              }`}
            >
              <MessageCircle className="h-5 w-5" />
            </button>
            <button
              onClick={() => setActiveTab("tasks")}
              className={`flex h-12 w-12 items-center justify-center rounded-2xl border transition-all ${
                activeTab === "tasks"
                  ? "border-[#7b61ff]/50 bg-[#7b61ff]/20 text-[#7b61ff] shadow-[0_0_15px_rgba(123,97,255,0.3)] scale-105"
                  : "border-transparent text-[#94a3b8] hover:bg-white/5 hover:text-white"
              }`}
            >
              <CheckCircle2 className="h-5 w-5" />
            </button>
            <button
              onClick={() => setActiveTab("calendar")}
              className={`flex h-12 w-12 items-center justify-center rounded-2xl border transition-all ${
                activeTab === "calendar"
                  ? "border-[#7b61ff]/50 bg-[#7b61ff]/20 text-[#7b61ff] shadow-[0_0_15px_rgba(123,97,255,0.3)] scale-105"
                  : "border-transparent text-[#94a3b8] hover:bg-white/5 hover:text-white"
              }`}
            >
              <Calendar className="h-5 w-5" />
            </button>
            <button
              onClick={() => setActiveTab("connection")}
              className={`flex h-12 w-12 items-center justify-center rounded-2xl border transition-all ${
                activeTab === "connection"
                  ? "border-[#7b61ff]/50 bg-[#7b61ff]/20 text-[#7b61ff] shadow-[0_0_15px_rgba(123,97,255,0.3)] scale-105"
                  : "border-transparent text-[#94a3b8] hover:bg-white/5 hover:text-white"
              }`}
              title="Connections"
            >
              <Smartphone className="h-5 w-5" />
            </button>
          </nav>
          
          <div className="mt-auto flex w-full flex-col items-center gap-4 hidden sm:flex">
            <button 
              onClick={async () => {
                setIsSyncing(true);
                try {
                  const res = await fetch(apiPath("/api/drive/sync"), { method: "POST" });
                  const data = await res.json();
                  if (data.status === "success") {
                    setAuthFlash({ type: "success", message: data.message || "Synced to Drive!" });
                  } else {
                    setAuthFlash({ type: "error", message: data.message || "Failed to sync" });
                  }
                } catch (e) {
                  setAuthFlash({ type: "error", message: "Network error during sync." });
                } finally {
                  setIsSyncing(false);
                }
              }}
              disabled={isSyncing}
              className="flex h-10 w-10 items-center justify-center rounded-xl text-[#94a3b8] transition-colors hover:bg-[#7b61ff]/20 hover:text-[#7b61ff] disabled:opacity-50" 
              title="Backup to Google Drive"
            >
              <CloudUpload className={`h-5 w-5 ${isSyncing ? "animate-bounce" : ""}`} />
            </button>
            <button onClick={handleSignOut} className="flex h-10 w-10 items-center justify-center rounded-xl text-[#94a3b8] transition-colors hover:bg-rose-500/20 hover:text-rose-400" title="Sign out">
              <LogOut className="h-5 w-5" />
            </button>
            <div className="mt-2 h-10 w-10 overflow-hidden rounded-full border border-white/20 bg-black shadow-[0_0_15px_rgba(255,255,255,0.1)]">
              {user?.photoURL ? (
                <Image src={user.photoURL} alt={user.displayName || "User"} width={40} height={40} />
              ) : (
                <div className="h-full w-full bg-gradient-to-tr from-cyan-500 to-blue-600" />
              )}
            </div>
          </div>
        </aside>

        {/* MAIN BODY */}
        <div className="flex min-w-0 flex-1 flex-col relative z-0">
          <header className="flex h-16 shrink-0 items-center justify-between border-b border-white/10 bg-black/20 px-6 backdrop-blur-xl">
            <div className="flex items-center gap-4">
              <button className="md:hidden text-[#94a3b8]"><Menu className="h-6 w-6" /></button>
              <div className="flex items-center gap-3">
                <div className="relative h-8 w-8 drop-shadow-[0_0_15px_rgba(123,97,255,0.5)]">
                  <Image src="/logo.png" alt="TaskForze Logo" fill priority className="object-contain" />
                </div>
                <h1 className="text-xl font-bold tracking-tight text-white">TaskForze</h1>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <span className="relative flex h-3 w-3">
                  <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-75 ${backendOnline ? 'bg-emerald-400' : 'bg-rose-400'}`} />
                  <span className={`relative inline-flex h-3 w-3 rounded-full ${backendOnline ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                </span>
                <span className="text-xs font-medium text-[#94a3b8] hidden sm:block">
                  {backendOnline ? 'Connected' : 'Reconnecting...'}
                </span>
              </div>
            </div>
          </header>

          <main className="min-h-0 flex-1 overflow-y-auto px-4 py-8 md:px-8">
            <div className="mx-auto max-w-6xl space-y-8">

              {authFlash && (
                <div className={`flex items-center gap-3 rounded-2xl p-4 font-medium backdrop-blur ${authFlash.type === "success" ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "bg-rose-500/10 text-rose-400 border border-rose-500/20"}`}>
                  <AlertCircle className="h-5 w-5 shrink-0" />
                  <p>{authFlash.message}</p>
                </div>
              )}
              
              {/* ASSISTANTS OVERVIEW */}
              <section className="rounded-3xl border border-white/10 bg-white/5 p-6 shadow-[0_8px_32px_rgba(0,0,0,0.5)] backdrop-blur-xl relative overflow-hidden">
                <div className="absolute inset-0 bg-gradient-to-br from-[#7b61ff]/5 to-transparent pointer-events-none" />
                <div className="mb-6 flex items-center justify-between relative z-10">
                  <div>
                    <h2 className="text-xl font-semibold text-white">Your Workforce</h2>
                    <p className="mt-1 text-sm text-white/50">
                      {liveAgents > 0 ? `${liveAgents} assistants actively working` : "All assistants standing by"}
                    </p>
                  </div>
                  <motion.div animate={{ rotate: liveAgents > 0 ? 180 : 0 }} transition={{ duration: 2, ease: "linear", repeat: liveAgents > 0 ? Infinity : 0 }}>
                    <Sparkles className="h-6 w-6 text-[#7b61ff]" />
                  </motion.div>
                </div>
                
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 relative z-10">
                  {agents.map((agent) => {
                    const isNotes = agent.name === "notes";
                    const isActive = agent.status !== "idle" || (isNotes && isRecording);
                    
                    return (
                      <motion.div
                        key={agent.name}
                        layout
                        onClick={isNotes ? toggleRecording : undefined}
                        animate={{
                          scale: isActive ? 1.02 : 1,
                          boxShadow: isActive ? "0 0 20px rgba(123, 97, 255, 0.4)" : "0 4px 6px -1px rgba(0, 0, 0, 0.1)",
                          borderColor: isActive ? "rgba(123, 97, 255, 0.5)" : "rgba(255, 255, 255, 0.05)",
                        }}
                        transition={{ type: "spring", stiffness: 300, damping: 20 }}
                        className={cn(
                          "group flex flex-col justify-between rounded-2xl border bg-black/40 p-4 transition-colors relative overflow-hidden",
                          isActive && "animate-pulse-glow",
                          isNotes && "cursor-pointer hover:bg-black/60",
                          isNotes && isRecording && "border-rose-500/50 shadow-[0_0_20px_rgba(244,63,94,0.4)]"
                        )}
                      >
                        {isActive && !isRecording && (
                          <div className="absolute top-0 left-0 w-1 h-full bg-[#7b61ff] shadow-[0_0_10px_#7b61ff]" />
                        )}
                        {isNotes && isRecording && (
                          <div className="absolute top-0 left-0 w-1 h-full bg-rose-500 shadow-[0_0_10px_#f43f5e]" />
                        )}
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-[#e2e8f0] drop-shadow-md">
                            {prettifyName(agent.name)}
                            {isNotes && isRecording && (
                              <span className="ml-2 inline-flex h-2 w-2 animate-ping rounded-full bg-rose-500" />
                            )}
                          </span>
                          {isRecording && isNotes ? (
                            <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/20 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-rose-400 border border-rose-500/30">
                              <Mic className="h-3 w-3" /> LISTENING
                            </span>
                          ) : isActive ? (
                            <span className="inline-flex items-center rounded-full bg-[#7b61ff]/20 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-[#9b87ff] border border-[#7b61ff]/30">
                              {agent.status}
                            </span>
                          ) : isNotes ? (
                            <span className="inline-flex items-center rounded-full bg-white/5 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-white/40 border border-white/10 group-hover:bg-white/10 group-hover:text-white/60 transition-colors">
                              <Mic className="h-3 w-3 mr-1" /> CLICK TO RECORD
                            </span>
                          ) : null}
                        </div>
                        <p className={cn("mt-2 text-sm line-clamp-2", (isActive || (isNotes && isRecording)) ? "text-white/90" : "text-white/40")}>
                          {isNotes && isRecording ? (recordingTranscript || "Listening for speech...") : agent.message}
                        </p>
                      </motion.div>
                    );
                  })}
                </div>
                
                {authStatus && !authStatus.authenticated && (
                  <div className="mt-6 flex flex-col sm:flex-row items-center justify-between gap-4 rounded-2xl border border-amber-500/20 bg-amber-500/5 p-5">
                    <div>
                      <h3 className="font-medium text-amber-200">Google Workspace Disconnected</h3>
                      <p className="text-sm text-amber-400/80 mt-1">Agents cannot read emails or manage your calendar until you grant permission.</p>
                    </div>
                    <a
                      href="http://localhost:8000/auth/login"
                      className="flex shrink-0 items-center gap-2 rounded-xl bg-amber-500/20 px-4 py-2.5 text-sm font-medium text-amber-300 transition-colors hover:bg-amber-500/30"
                    >
                      Connect <ExternalLink className="h-4 w-4" />
                    </a>
                  </div>
                )}
              </section>

              {/* TABS CONTENT */}
              <AnimatePresence mode="popLayout" initial={false}>
                {activeTab === "chat" && (
                  <motion.div 
                    key="chat-view"
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    transition={{ duration: 0.3 }}
                    className="grid grid-cols-1 gap-6 lg:grid-cols-3 xl:gap-8"
                  >
                    <section className="flex h-[600px] flex-col overflow-hidden rounded-3xl border border-white/10 bg-white/5 shadow-[0_8px_32px_rgba(0,0,0,0.3)] backdrop-blur-3xl lg:col-span-2 relative">
                      <div className="absolute inset-0 bg-gradient-to-br from-black/40 to-transparent pointer-events-none" />
                      
                      {/* Chat Header */}
                      <div className="flex items-center gap-3 border-b border-white/10 bg-black/20 p-4 relative overflow-hidden backdrop-blur-xl z-10">
                        <div className="absolute inset-x-0 bottom-0 h-[1px] bg-gradient-to-r from-transparent via-[#7b61ff]/50 to-transparent" />
                        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-[#7b61ff] to-[#4c2dff] shadow-[0_0_15px_rgba(123,97,255,0.4)]">
                          <Bot className="h-5 w-5 text-white" />
                        </div>
                        <div>
                          <h2 className="font-semibold text-white drop-shadow-md">Ask TaskForze</h2>
                          <div className="flex items-center gap-2 text-xs text-[#7b61ff]">
                            <span className="relative flex h-2 w-2">
                              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#7b61ff] opacity-75"></span>
                              <span className="relative inline-flex h-2 w-2 rounded-full bg-[#7b61ff]"></span>
                            </span>
                            Online & Ready
                          </div>
                        </div>
                      </div>

                      {/* Messages Area */}
                      <div className="flex-1 overflow-y-auto p-6 scroll-smooth z-10">
                        {messages.length === 0 ? (
                          <div className="flex h-full flex-col items-center justify-center text-center">
                            <div className="rounded-full bg-white/5 p-6 border border-white/10 mb-4 shadow-[0_0_30px_rgba(123,97,255,0.15)] relative">
                              <div className="absolute inset-0 bg-gradient-to-tr from-[#7b61ff]/20 to-transparent rounded-full animate-pulse-glow" />
                              <Hexagon className="h-10 w-10 text-[#7b61ff]/70 relative z-10" />
                            </div>
                            <h3 className="text-xl font-bold text-white drop-shadow-md">How can we help today?</h3>
                            <p className="mt-3 max-w-sm text-sm text-white/50 leading-relaxed">
                              Delegate tasks to your AI workforce. Ask us to draft emails, analyze files, check calendars, and more.
                            </p>
                          </div>
                        ) : (
                          <div className="space-y-6">
                            {messages.map((m, i) => (
                              <motion.div 
                                initial={{ opacity: 0, y: 10, scale: 0.98 }}
                                animate={{ opacity: 1, y: 0, scale: 1 }}
                                key={i} 
                                className={`flex gap-4 ${m.role === "user" ? "justify-end" : "justify-start"}`}
                              >
                                {m.role === "assistant" && (
                                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-[#7b61ff] to-[#4c2dff] shadow-[0_0_15px_rgba(123,97,255,0.3)]">
                                    <Sparkles className="h-4 w-4 text-white" />
                                  </div>
                                )}
                                <div className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-5 py-4 text-sm leading-relaxed shadow-lg backdrop-blur-md ${m.role === "user" ? "rounded-br-sm bg-gradient-to-tr from-white to-gray-200 text-black font-medium" : "rounded-bl-sm border border-white/10 bg-black/40 text-[#e2e8f0]"}`}>
                                  {m.content}
                                </div>
                                {m.role === "user" && (
                                  <div className="h-8 w-8 shrink-0 overflow-hidden rounded-xl border border-white/20 bg-black shadow-[0_0_10px_rgba(255,255,255,0.1)]">
                                    {user?.photoURL && <Image src={user.photoURL} alt="User" width={32} height={32} />}
                                  </div>
                                )}
                              </motion.div>
                            ))}
                            {isLoading && (
                              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-4">
                                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-black/40 border border-white/10">
                                  <div className="h-3 w-3 animate-ping rounded-full bg-[#7b61ff]" />
                                </div>
                                <div className="rounded-2xl rounded-bl-sm border border-[#7b61ff]/30 bg-[#7b61ff]/10 px-5 py-4 text-sm text-[#9b87ff] flex items-center gap-2">
                                  <span className="relative flex h-2 w-2">
                                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#7b61ff] opacity-75"></span>
                                    <span className="relative inline-flex h-2 w-2 rounded-full bg-[#7b61ff]"></span>
                                  </span>
                                  Workforce orchestrating...
                                </div>
                              </motion.div>
                            )}
                            <div ref={messagesEndRef} />
                          </div>
                        )}
                      </div>

                      <div className="border-t border-white/10 bg-black/20 p-4 backdrop-blur-xl z-10">
                        <form onSubmit={(e) => { e.preventDefault(); void handleSubmit(); }} className="flex gap-3 relative">
                          <input
                            type="text"
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            placeholder="Delegate a task to your workforce..."
                            className="flex-1 rounded-2xl border border-white/10 bg-white/5 px-5 py-4 text-sm text-white placeholder-white/40 focus:border-[#7b61ff]/50 focus:bg-black/40 focus:outline-none focus:ring-1 focus:ring-[#7b61ff]/50 transition-all backdrop-blur-md shadow-inner"
                            disabled={isLoading}
                          />
                          <button
                            type="submit"
                            disabled={isLoading || !input.trim()}
                            className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-tr from-[#7b61ff] to-[#4c2dff] text-white shadow-[0_0_20px_rgba(123,97,255,0.4)] transition-all hover:scale-105 hover:shadow-[0_0_30px_rgba(123,97,255,0.6)] disabled:opacity-50 disabled:hover:scale-100 disabled:hover:shadow-[0_0_20px_rgba(123,97,255,0.4)]"
                          >
                            <Send className="h-5 w-5 ml-1" />
                          </button>
                        </form>
                      </div>
                    </section>

                    {/* SIDE PANELS */}
                    <div className="flex flex-col gap-6">
                      <section className="flex min-h-[300px] flex-col rounded-3xl border border-white/10 bg-white/5 py-6 px-4 shadow-[0_8px_32px_rgba(0,0,0,0.3)] backdrop-blur-2xl relative overflow-hidden">
                        <div className="absolute inset-x-0 top-0 h-[1px] bg-gradient-to-r from-transparent via-emerald-500/50 to-transparent" />
                        <div className="mb-4 flex items-center justify-between px-2">
                          <h3 className="font-bold text-white drop-shadow-md">Up Next</h3>
                          <Clock className="h-4 w-4 text-emerald-400" />
                        </div>
                        <div className="flex flex-col gap-3 overflow-y-auto px-2 pb-2">
                          {tasks.slice(0, 4).map((task) => (
                            <motion.div whileHover={{ scale: 1.02 }} key={task.id} className="group flex items-start gap-3 rounded-2xl border border-white/5 bg-black/40 p-3 relative overflow-hidden transition-all hover:border-emerald-500/30 hover:bg-emerald-500/5 cursor-default">
                              <div className="mt-0.5 rounded-full border border-white/20 p-0.5 text-transparent transition-colors group-hover:border-emerald-500 group-hover:text-emerald-400">
                                <CheckCircle2 className="h-3 w-3" />
                              </div>
                              <div className="min-w-0 flex-1">
                                <p className="text-sm font-medium text-white truncate text-shadow-sm">{task.title}</p>
                              </div>
                            </motion.div>
                          ))}
                          {tasks.length === 0 && (
                            <p className="text-sm text-white/40 text-center mt-8">No tasks on your radar.</p>
                          )}
                        </div>
                      </section>

                      <section className="flex flex-col flex-1 rounded-3xl border border-white/10 bg-white/5 py-6 px-4 shadow-[0_8px_32px_rgba(0,0,0,0.3)] backdrop-blur-2xl relative overflow-hidden">
                        <div className="absolute inset-x-0 top-0 h-[1px] bg-gradient-to-r from-transparent via-[#7b61ff]/50 to-transparent" />
                        <div className="mb-4 flex items-center justify-between px-2">
                          <h3 className="font-bold text-white drop-shadow-md">Activity</h3>
                          <Activity className="h-4 w-4 text-[#7b61ff]" />
                        </div>
                        <div className="flex flex-col gap-4 px-2">
                          {workflows.slice(0, 4).map((w) => (
                            <div key={w.id} className="relative pl-5 border-l border-white/10">
                              <div className="absolute -left-[5px] top-1.5 h-2 w-2 rounded-full bg-[#7b61ff] shadow-[0_0_8px_#7b61ff]" />
                              <p className="text-[9px] font-bold uppercase tracking-widest text-[#9b87ff]">Completed</p>
                              <p className="mt-0.5 text-sm font-medium text-white line-clamp-2">{w.original_request}</p>
                            </div>
                          ))}
                          {workflows.length === 0 && (
                            <p className="text-sm text-white/40 text-center mt-8">No recent activity.</p>
                          )}
                        </div>
                      </section>
                    </div>
                  </motion.div>
                )}

                {activeTab === "tasks" && (
                  <motion.div 
                    key="tasks-view"
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    transition={{ duration: 0.3 }}
                    className="flex flex-col rounded-3xl border border-white/10 bg-white/5 p-8 shadow-[0_8px_32px_rgba(0,0,0,0.5)] backdrop-blur-3xl min-h-[600px] relative overflow-hidden"
                  >
                    <div className="absolute inset-0 bg-gradient-to-bl from-emerald-500/5 to-transparent pointer-events-none" />
                    <div className="mb-6 flex items-center gap-3 relative z-10">
                      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-400 to-emerald-600 shadow-[0_0_15px_rgba(52,211,153,0.4)]">
                        <CheckCircle2 className="h-6 w-6 text-white" />
                      </div>
                      <h2 className="text-2xl font-bold text-white drop-shadow-md">All Tasks</h2>
                    </div>
                    {tasks.length === 0 ? (
                      <div className="flex flex-1 flex-col items-center justify-center text-center p-12 relative z-10">
                        <div className="rounded-full bg-white/5 p-6 border border-white/10 mb-4 shadow-xl">
                          <CheckCircle2 className="h-10 w-10 text-white/20" />
                        </div>
                        <h3 className="text-lg font-bold text-white mb-2 drop-shadow">No active tasks</h3>
                        <p className="text-white/50 max-w-sm">Delegate tasks to your AI workforce using the chat interface.</p>
                      </div>
                    ) : (
                      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3 relative z-10">
                        {tasks.map((task) => (
                          <motion.div whileHover={{ y: -4 }} key={task.id} className="group rounded-2xl border border-white/10 bg-black/40 p-5 relative overflow-hidden shadow-lg transition-all hover:bg-white/5 hover:border-emerald-500/30">
                             <div className="absolute top-0 right-0 p-4 opacity-5 pointer-events-none">
                               <CheckCircle2 className="h-24 w-24 text-emerald-400 transform rotate-12 transition-transform group-hover:scale-110 group-hover:rotate-6" />
                             </div>
                             <h4 className="text-lg font-bold text-white mb-2 truncate relative z-10 text-shadow-sm">{task.title}</h4>
                             <p className="text-sm text-white/60 mb-5 relative z-10 line-clamp-3">{task.description}</p>
                             <div className="flex items-center gap-2 relative z-10">
                               <span className="inline-flex rounded-full bg-emerald-500/10 px-3 py-1.5 text-[11px] font-bold tracking-wide uppercase text-emerald-400 border border-emerald-500/20 shadow-inner">
                                 Pending
                               </span>
                             </div>
                          </motion.div>
                        ))}
                      </div>
                    )}
                  </motion.div>
                )}

                {activeTab === "calendar" && (
                  <motion.div 
                    key="calendar-view"
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    transition={{ duration: 0.3 }}
                    className="flex flex-col items-center justify-center flex-1 min-h-[600px] rounded-3xl border border-white/10 bg-white/5 p-8 shadow-[0_8px_32px_rgba(0,0,0,0.5)] backdrop-blur-3xl relative overflow-hidden"
                  >
                    <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_rgba(123,97,255,0.1),_transparent_70%)] pointer-events-none" />
                    <div className="rounded-full bg-white/5 p-8 border border-white/10 mb-6 relative overflow-hidden shadow-2xl">
                      <div className="absolute inset-0 bg-gradient-to-tr from-[#7b61ff]/20 to-transparent animate-pulse-glow pointer-events-none" />
                      <Calendar className="h-12 w-12 text-[#7b61ff]/80 relative z-10" />
                    </div>
                    <h2 className="text-3xl font-bold text-white mb-3 drop-shadow-md tracking-tight">Calendar</h2>
                    <p className="text-white/50 max-w-md text-center text-lg leading-relaxed">Your full intelligent schedule overview is coming soon to the glass interface.</p>
                  </motion.div>
                )}

                {activeTab === "connection" && (
                  <motion.div 
                    key="connection-view"
                    initial={{ opacity: 0, scale: 0.98 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.98 }}
                    transition={{ duration: 0.2 }}
                    className="flex flex-col rounded-3xl border border-white/10 bg-[#161618] shadow-2xl overflow-hidden min-h-[600px] flex-1 relative"
                  >
                    {/* Top Search bar area */}
                    <div className="p-4 border-b border-white/10 bg-[#1c1c1e]">
                      <div className="relative max-w-full">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-white/40" />
                        <input 
                          type="text" 
                          placeholder="Search connectors..." 
                          value={searchQuery}
                          onChange={(e) => setSearchQuery(e.target.value)}
                          className="w-full bg-[#252528] border border-transparent rounded-lg pl-11 pr-4 py-2.5 text-sm text-white placeholder-white/40 focus:outline-none focus:border-white/20 transition-all hover:bg-[#2a2a2d]" 
                        />
                      </div>
                    </div>

                    <div className="p-6 md:p-8 flex-1 overflow-y-auto">
                      {/* Filter / Sort Row */}
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
                        <div className="flex items-center gap-2">
                          <button className="bg-black rounded-full px-4 py-1.5 text-xs font-semibold text-white border border-white/10 hover:bg-white/5 transition-colors">
                            All Integrations
                          </button>
                        </div>
                        <div className="flex items-center gap-3">
                          <button className="flex items-center gap-2 bg-[#252528] border border-white/5 rounded-md px-3 py-1.5 text-sm font-medium text-white/70 hover:bg-[#2a2a2d] transition-colors">
                            Filter by <ChevronDown className="h-4 w-4 opacity-60" />
                          </button>
                          <button className="flex items-center gap-2 bg-[#252528] border border-white/5 rounded-md px-3 py-1.5 text-sm font-medium text-white/70 hover:bg-[#2a2a2d] transition-colors">
                            Sort by <ChevronDown className="h-4 w-4 opacity-60" />
                          </button>
                        </div>
                      </div>

                      {/* Grid of Cards */}
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {connectors
                          .filter(c => c.name.toLowerCase().includes(searchQuery.toLowerCase()) || c.desc.toLowerCase().includes(searchQuery.toLowerCase()))
                          .map(c => (
                          <div key={c.id} className="group rounded-2xl border border-white/10 bg-[#1e1e20] p-5 hover:bg-[#252528] transition-colors flex flex-col gap-3">
                            {/* Top line: Icon, Title, and Plus button */}
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-3">
                                <div className="flex shrink-0 items-center justify-center w-10 h-10 rounded-xl bg-[#2a2a2d] border border-white/5 shadow-inner">
                                  {c.icon}
                                </div>
                                <span className="text-white font-semibold text-[15px]">{c.name}</span>
                              </div>
                              <button className="text-white/40 hover:text-white hover:bg-white/10 rounded-full p-1.5 transition-colors flex shrink-0" title={`Connect ${c.name}`}>
                                <Plus className="w-5 h-5" />
                              </button>
                            </div>
                            {/* Bottom line: Description */}
                            <p className="text-white/50 text-[13px] leading-relaxed">
                              {c.desc}
                            </p>
                          </div>
                        ))}
                      </div>

                      {connectors.filter(c => c.name.toLowerCase().includes(searchQuery.toLowerCase()) || c.desc.toLowerCase().includes(searchQuery.toLowerCase())).length === 0 && (
                        <div className="text-center text-white/50 py-12">
                          No connectors found matching "{searchQuery}"
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </main>
        </div>
      </div>
    </AuthGuard>
  );
}

