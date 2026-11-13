import { useEffect, useState } from "react";

type Job = {
  job_id: string; project_id: string; name: string; status: string;
  stage: string; progress: number; error_message?: string | null;
  created_at: string;
};

type Props = {
  projectId: string;
  apiBaseUrl?: string;
  accessToken: string;
};

export default function ProcessingWorkspace({
  projectId, apiBaseUrl = "", accessToken
}: Props) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [name, setName] = useState("Dataset processing");
  const [sourceIds, setSourceIds] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const headers = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${accessToken}`
  };

  async function refresh() {
    const response = await fetch(
      `${apiBaseUrl}/api/v1/jobs?project_id=${encodeURIComponent(projectId)}`,
      { headers }
    );
    if (!response.ok) throw new Error(`Could not load jobs (${response.status}).`);
    setJobs(await response.json());
  }

  useEffect(() => {
    refresh().catch(e => setError(e.message));
    const timer = window.setInterval(() => refresh().catch(() => {}), 4000);
    return () => window.clearInterval(timer);
  }, [projectId, accessToken]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const ids = sourceIds.split(",").map(x => x.trim()).filter(Boolean);
      const response = await fetch(`${apiBaseUrl}/api/v1/jobs`, {
        method: "POST", headers,
        body: JSON.stringify({
          project_id: projectId, name, source_ids: ids, pipeline: "standard"
        })
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Could not submit job.");
      setSourceIds("");
      await refresh();
    } catch (e: any) {
      setError(e.message || "Request failed.");
    } finally { setBusy(false); }
  }

  async function jobAction(jobId: string, action: "cancel" | "retry") {
    const response = await fetch(
      `${apiBaseUrl}/api/v1/jobs/${jobId}/${action}`,
      { method: "POST", headers }
    );
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || `Could not ${action} job.`);
    await refresh();
  }

  return (
    <section className="space-y-6 text-slate-100">
      <header>
        <h1 className="text-2xl font-semibold">Processing</h1>
        <p className="mt-1 text-sm text-slate-400">
          Submit source files and monitor processing jobs.
        </p>
      </header>

      <form onSubmit={submit} className="grid gap-3 rounded-xl border border-slate-700 bg-slate-900 p-5">
        <label className="text-sm">Job name
          <input value={name} onChange={e => setName(e.target.value)}
            required minLength={2} maxLength={200}
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 p-3" />
        </label>
        <label className="text-sm">Source IDs (comma separated)
          <input value={sourceIds} onChange={e => setSourceIds(e.target.value)}
            required placeholder="Paste source IDs from this project"
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 p-3" />
        </label>
        <button disabled={busy}
          className="w-fit rounded-lg bg-amber-400 px-5 py-2 font-semibold text-slate-950 disabled:opacity-50">
          {busy ? "Submitting…" : "Start processing"}
        </button>
      </form>

      {error && <p role="alert" className="text-sm text-red-400">{error}</p>}

      <div className="space-y-3">
        {jobs.map(job => (
          <article key={job.job_id} className="rounded-xl border border-slate-700 bg-slate-900 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="font-medium">{job.name}</h2>
                <p className="text-xs text-slate-400">{job.job_id}</p>
              </div>
              <span className="rounded-full bg-slate-800 px-3 py-1 text-xs">{job.status}</span>
            </div>
            <p className="mt-3 text-sm text-slate-400">{job.stage}</p>
            <div className="mt-2 h-2 overflow-hidden rounded bg-slate-800">
              <div className="h-full bg-amber-400 transition-all"
                style={{ width: `${job.progress}%` }} />
            </div>
            <div className="mt-2 flex justify-between text-xs text-slate-400">
              <span>{job.progress}%</span>
              <span>{new Date(job.created_at).toLocaleString()}</span>
            </div>
            {job.error_message && <p className="mt-2 text-sm text-red-400">{job.error_message}</p>}
            <div className="mt-3 flex gap-2">
              {["queued", "running"].includes(job.status) &&
                <button onClick={() => jobAction(job.job_id, "cancel")}
                  className="rounded border border-slate-600 px-3 py-1 text-xs">Cancel</button>}
              {["failed", "cancelled"].includes(job.status) &&
                <button onClick={() => jobAction(job.job_id, "retry").catch(e => setError(e.message))}
                  className="rounded border border-slate-600 px-3 py-1 text-xs">Retry</button>}
            </div>
          </article>
        ))}
        {jobs.length === 0 && <p className="text-sm text-slate-400">No processing jobs yet.</p>}
      </div>
    </section>
  );
}
