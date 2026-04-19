import { useEffect, useState } from "react";
import { Gauge, Leaf, Mountain, Shuffle } from "lucide-react";
import BackgroundGlow from "./components/BackgroundGlow";
import CommandCard from "./components/CommandCard";
import LoadComparisonChart from "./components/LoadComparisonChart";
import MetricCard from "./components/MetricCard";
import StressTimeline from "./components/StressTimeline";
import TopBar from "./components/TopBar";
import WorkloadShiftTable from "./components/WorkloadShiftTable";
import {
  dashboardMetrics,
  profileData,
  scenarioOptions,
  workloadShifts,
} from "./data/mockData";
import { API_BASE_URL, getDemoScenario, getHealth, optimizeSchedule } from "./services/api";

function toNumber(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function parseHour(value, fallback = 0) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return ((Math.trunc(value) % 24) + 24) % 24;
  }

  if (typeof value === "string") {
    const trimmed = value.trim();
    if (/^\d{1,2}$/.test(trimmed)) {
      return ((Number.parseInt(trimmed, 10) % 24) + 24) % 24;
    }
    if (/^\d{1,2}:\d{2}/.test(trimmed)) {
      return ((Number.parseInt(trimmed.split(":")[0], 10) % 24) + 24) % 24;
    }
    const date = new Date(trimmed);
    if (!Number.isNaN(date.getTime())) {
      return date.getHours();
    }
  }

  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return value.getHours();
  }

  return ((Math.trunc(fallback) % 24) + 24) % 24;
}

function normalizeProfile(profile) {
  if (!Array.isArray(profile)) return [];
  const byHour = new Map();

  profile.forEach((point, index) => {
    const hour = parseHour(point?.hour, index);
    const load = toNumber(point?.load_mw, toNumber(point?.loadMw, 0));
    const stress = toNumber(point?.grid_stress, toNumber(point?.gridStress, 0));
    byHour.set(hour, {
      hour,
      load_mw: Math.max(0, load),
      grid_stress: Math.min(1, Math.max(0, stress)),
    });
  });

  if (byHour.size !== 24) return [];
  const normalized = [];
  for (let hour = 0; hour < 24; hour += 1) {
    const point = byHour.get(hour);
    if (!point) return [];
    normalized.push(point);
  }
  return normalized;
}

function normalizeWorkloads(workloads) {
  if (!Array.isArray(workloads)) return [];

  return workloads.map((job, index) => {
    const earliestStart = toNumber(job?.earliest_start, 0);
    const startHour = toNumber(job?.start_hour, earliestStart);
    const currentStart = toNumber(job?.current_start_hour, startHour);

    return {
      id: String(job?.id ?? `job_${index + 1}`),
      name: String(job?.name ?? `Workload ${index + 1}`),
      duration_hours: Math.max(1, Math.min(24, toNumber(job?.duration_hours, 1))),
      earliest_start: Math.max(0, Math.min(23, earliestStart)),
      latest_finish: Math.max(0, Math.min(24, toNumber(job?.latest_finish, 24))),
      priority: job?.priority === "critical" ? "critical" : "flexible",
      power_mw: Math.max(0.1, toNumber(job?.power_mw, 0.1)),
      current_start_hour: Math.max(0, Math.min(23, currentStart)),
      start_hour: Math.max(0, Math.min(23, startHour)),
    };
  });
}

function buildChartData(baselineProfile, optimizedProfile) {
  const baseline = normalizeProfile(baselineProfile);
  const optimized = normalizeProfile(optimizedProfile);
  if (baseline.length !== 24 || optimized.length !== 24) return profileData;

  return baseline.map((point, hour) => ({
    hour: `${String(hour).padStart(2, "0")}:00`,
    baselineLoad: toNumber(point.load_mw, 0),
    optimizedLoad: toNumber(optimized[hour]?.load_mw, toNumber(point.load_mw, 0)),
    gridStress: toNumber(point.grid_stress, 0),
  }));
}

function mapWorkloadsToRows(workloads) {
  return workloads.map((job) => {
    const startHour = toNumber(job.current_start_hour, toNumber(job.start_hour, job.earliest_start));
    return {
      id: job.id,
      name: job.name,
      priority: job.priority,
      originalHour: startHour,
      newHour: startHour,
      powerMw: toNumber(job.power_mw, 0),
      durationHours: toNumber(job.duration_hours, 1),
      moved: false,
      reason:
        job.priority === "critical"
          ? "Kept in place because workload is marked critical."
          : "Awaiting optimization run.",
    };
  });
}

function applyAssignmentsToWorkloads(workloads, assignments) {
  const byId = new Map((assignments || []).map((item) => [item.job_id, item]));
  return workloads.map((job) => {
    const assignment = byId.get(job.id);
    if (!assignment) return job;
    const start = Math.max(0, Math.min(23, toNumber(assignment.start_hour, job.current_start_hour)));
    return {
      ...job,
      current_start_hour: start,
      start_hour: start,
    };
  });
}

function buildScheduleRows(scheduleChanges, assignments, workloads) {
  const assignmentById = new Map((assignments || []).map((item) => [item.job_id, item]));
  const workloadById = new Map((workloads || []).map((item) => [item.id, item]));

  if (!Array.isArray(scheduleChanges) || scheduleChanges.length === 0) {
    return mapWorkloadsToRows(workloads || []);
  }

  return scheduleChanges.map((change) => {
    const jobId = String(change.job_id);
    const assignment = assignmentById.get(jobId);
    const workload = workloadById.get(jobId);

    return {
      id: jobId,
      name: String(change.job_name ?? workload?.name ?? jobId),
      priority: String(change.priority ?? workload?.priority ?? "flexible"),
      originalHour: toNumber(change.old_start_hour, toNumber(workload?.current_start_hour, 0)),
      newHour: toNumber(change.new_start_hour, toNumber(assignment?.start_hour, 0)),
      powerMw: toNumber(assignment?.power_mw, toNumber(workload?.power_mw, 0)),
      durationHours: toNumber(assignment?.duration_hours, toNumber(workload?.duration_hours, 1)),
      moved: Boolean(change.moved),
      reason: String(change.reason ?? "Schedule updated."),
    };
  });
}

function countFlexibleJobs(workloads) {
  return workloads.filter((job) => job.priority === "flexible").length;
}

function mapMetrics(metricsPayload, workloads, scheduleRows) {
  const jobsShiftedFallback = scheduleRows.filter(
    (row) => row.priority === "flexible" && row.moved
  ).length;

  return {
    peakOverlapReduction: toNumber(
      metricsPayload?.peak_overlap_reduction,
      dashboardMetrics.peakOverlapReduction
    ),
    jobsShifted: toNumber(metricsPayload?.jobs_shifted, jobsShiftedFallback),
    totalFlexibleJobs: countFlexibleJobs(workloads),
    gridFriendlinessBefore: toNumber(
      metricsPayload?.grid_friendliness_score_before,
      dashboardMetrics.gridFriendlinessBefore
    ),
    gridFriendlinessAfter: toNumber(
      metricsPayload?.grid_friendliness_score_after,
      dashboardMetrics.gridFriendlinessAfter
    ),
    peakLoadBefore: toNumber(metricsPayload?.peak_load_before, dashboardMetrics.peakLoadBefore),
    peakLoadAfter: toNumber(metricsPayload?.peak_load_after, dashboardMetrics.peakLoadAfter),
  };
}

function makeOptimizePayload(profile, workloads) {
  return {
    profile: profile.map((point) => ({
      hour: point.hour,
      load_mw: toNumber(point.load_mw, 0),
      grid_stress: toNumber(point.grid_stress, 0),
    })),
    workloads: workloads.map((job) => ({
      id: job.id,
      name: job.name,
      duration_hours: toNumber(job.duration_hours, 1),
      earliest_start: toNumber(job.earliest_start, 0),
      latest_finish: toNumber(job.latest_finish, 24),
      priority: job.priority,
      power_mw: toNumber(job.power_mw, 0),
      current_start_hour: toNumber(job.current_start_hour, 0),
      start_hour: toNumber(job.start_hour, 0),
    })),
  };
}

function round2(value) {
  return Math.round(value * 100) / 100;
}

function estimateGridFriendliness(profile) {
  const normalized = normalizeProfile(profile);
  if (normalized.length !== 24) return dashboardMetrics.gridFriendlinessBefore;

  const loads = normalized.map((p) => toNumber(p.load_mw, 0));
  const stress = normalized.map((p) => toNumber(p.grid_stress, 0));
  const meanLoad = loads.reduce((acc, v) => acc + v, 0) / loads.length;
  const maxStress = Math.max(...stress, 0);

  if (meanLoad <= 0 || maxStress <= 0) return 100;

  const overlapAvg =
    normalized.reduce((acc, p) => acc + toNumber(p.load_mw, 0) * toNumber(p.grid_stress, 0), 0) /
    normalized.length;
  const overlapNorm = overlapAvg / (meanLoad * maxStress + 1e-9);

  const peakRatio = Math.max(...loads) / (meanLoad + 1e-9);
  const peakPenaltyNorm = Math.min(1, Math.max(0, (peakRatio - 1) / 2));

  const raw = 100 * (1 - 0.9 * overlapNorm - 0.1 * peakPenaltyNorm);
  return Math.max(0, Math.min(100, raw));
}

function fallbackWorkloadsFromRows(rows) {
  return (rows || []).map((row) => ({
    id: row.id,
    name: row.name,
    duration_hours: Math.max(1, Math.min(24, toNumber(row.durationHours, 1))),
    earliest_start: Math.max(0, Math.min(23, toNumber(row.originalHour, 0))),
    latest_finish: 24,
    priority: row.priority === "critical" ? "critical" : "flexible",
    power_mw: Math.max(0.1, toNumber(row.powerMw, 0.1)),
    current_start_hour: Math.max(0, Math.min(23, toNumber(row.originalHour, 0))),
    start_hour: Math.max(0, Math.min(23, toNumber(row.originalHour, 0))),
  }));
}

function buildScenarioVariant(baseProfile, baseWorkloads, scenarioName) {
  const normalizedBase = normalizeProfile(baseProfile);
  const workloads = normalizeWorkloads(baseWorkloads);
  if (normalizedBase.length !== 24 || workloads.length === 0) {
    return { profile: normalizedBase, workloads };
  }

  const scenario = String(scenarioName || "");
  const profile = normalizedBase.map((point) => {
    const hour = toNumber(point.hour, 0);
    const isDay = hour >= 8 && hour <= 19;
    const isEveningPeak = hour >= 16 && hour <= 21;

    let load = toNumber(point.load_mw, 0);
    let stress = toNumber(point.grid_stress, 0);

    if (scenario.includes("Summer")) {
      load = load * (isDay ? 1.11 : 1.04) + (isEveningPeak ? 0.45 : 0);
      stress = stress * (isDay ? 1.14 : 1.06) + (isEveningPeak ? 0.07 : 0.02);
    } else if (scenario.includes("Weekend")) {
      load = load * (isDay ? 0.86 : 0.92) - (isEveningPeak ? 0.25 : 0.1);
      stress = stress * (isDay ? 0.72 : 0.8) - (isEveningPeak ? 0.09 : 0.04);
    } else {
      load = load;
      stress = stress;
    }

    return {
      hour,
      load_mw: round2(Math.max(6, load)),
      grid_stress: round2(Math.max(0.05, Math.min(0.99, stress))),
    };
  });

  const workloadShiftHours = scenario.includes("Weekend")
    ? { startShift: -1 }
    : scenario.includes("Summer")
      ? { startShift: 1 }
      : { startShift: 0 };

  const shiftedWorkloads = workloads.map((job) => {
    if (job.priority === "critical") return job;
    const shifted = (toNumber(job.current_start_hour, 0) + workloadShiftHours.startShift + 24) % 24;
    return {
      ...job,
      current_start_hour: shifted,
      start_hour: shifted,
    };
  });

  return { profile, workloads: shiftedWorkloads };
}

export default function App() {
  const [selectedScenario, setSelectedScenario] = useState(scenarioOptions[0]);
  const [lastOptimizedAt, setLastOptimizedAt] = useState(new Date());
  const [isRunning, setIsRunning] = useState(false);
  const [backendConnected, setBackendConnected] = useState(false);
  const [modelLoaded, setModelLoaded] = useState(false);
  const [backendMessage, setBackendMessage] = useState("Checking backend...");

  const [chartData, setChartData] = useState(profileData);
  const [workloadRows, setWorkloadRows] = useState(workloadShifts);
  const [metrics, setMetrics] = useState(dashboardMetrics);
  const [rawProfile, setRawProfile] = useState([]);
  const [rawWorkloads, setRawWorkloads] = useState([]);
  const [baseScenarioProfile, setBaseScenarioProfile] = useState([]);
  const [baseScenarioWorkloads, setBaseScenarioWorkloads] = useState([]);

  useEffect(() => {
    let cancelled = false;

    async function initializeFromBackend() {
      setBackendMessage(`Connecting to ${API_BASE_URL}`);
      try {
        const health = await getHealth();
        if (cancelled) return;

        setBackendConnected(true);
        setModelLoaded(Boolean(health.model_loaded));
        setBackendMessage(`Connected to ${API_BASE_URL}`);

        const scenario = await getDemoScenario();
        if (cancelled) return;

        const profile = normalizeProfile(scenario.profile);
        const workloads = normalizeWorkloads(scenario.workloads);

        if (profile.length !== 24 || workloads.length === 0) {
          throw new Error("Demo scenario payload is missing required fields.");
        }

        setBaseScenarioProfile(profile);
        setBaseScenarioWorkloads(workloads);
      } catch (error) {
        if (cancelled) return;
        setBackendConnected(false);
        setModelLoaded(false);
        setBackendMessage(`Backend unavailable at ${API_BASE_URL}`);
        const fallbackProfile = normalizeProfile(profileData.map((p, hour) => ({
          hour,
          load_mw: p.baselineLoad,
          grid_stress: p.gridStress,
        })));
        const fallbackWorkloads = fallbackWorkloadsFromRows(workloadShifts);

        if (fallbackProfile.length === 24 && fallbackWorkloads.length > 0) {
          setBaseScenarioProfile(fallbackProfile);
          setBaseScenarioWorkloads(fallbackWorkloads);
        }
      }
    }

    initializeFromBackend();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (baseScenarioProfile.length !== 24 || baseScenarioWorkloads.length === 0) return;

    const { profile, workloads } = buildScenarioVariant(
      baseScenarioProfile,
      baseScenarioWorkloads,
      selectedScenario
    );

    if (profile.length !== 24 || workloads.length === 0) return;

    const baselinePeak = Math.max(...profile.map((point) => toNumber(point.load_mw, 0)));
    const baseFriendliness = estimateGridFriendliness(profile);

    setRawProfile(profile);
    setRawWorkloads(workloads);
    setChartData(buildChartData(profile, profile));
    setWorkloadRows(mapWorkloadsToRows(workloads));
    setMetrics((prev) => ({
      ...prev,
      peakOverlapReduction: 0,
      jobsShifted: 0,
      totalFlexibleJobs: countFlexibleJobs(workloads),
      gridFriendlinessBefore: baseFriendliness,
      gridFriendlinessAfter: baseFriendliness,
      peakLoadBefore: baselinePeak,
      peakLoadAfter: baselinePeak,
    }));
  }, [selectedScenario, baseScenarioProfile, baseScenarioWorkloads]);

  const handleOptimize = async () => {
    if (isRunning) return;
    setIsRunning(true);

    try {
      let profile = rawProfile;
      let workloads = rawWorkloads;

      if (profile.length !== 24 || workloads.length === 0) {
        const scenario = await getDemoScenario();
        profile = normalizeProfile(scenario.profile);
        workloads = normalizeWorkloads(scenario.workloads);
      }

      if (profile.length !== 24 || workloads.length === 0) {
        throw new Error("No valid scenario loaded to optimize.");
      }

      const result = await optimizeSchedule(makeOptimizePayload(profile, workloads));
      const baselineProfile = normalizeProfile(result.baseline_profile);
      const optimizedProfile = normalizeProfile(result.optimized_profile);
      const assignments = Array.isArray(result.job_assignments) ? result.job_assignments : [];

      if (baselineProfile.length === 24 && optimizedProfile.length === 24) {
        setChartData(buildChartData(baselineProfile, optimizedProfile));
      }

      const updatedWorkloads = applyAssignmentsToWorkloads(workloads, assignments);
      const scheduleRows = buildScheduleRows(result.schedule_changes, assignments, updatedWorkloads);

      setRawWorkloads(updatedWorkloads);
      setWorkloadRows(scheduleRows);
      setMetrics(mapMetrics(result.metrics, updatedWorkloads, scheduleRows));
      setLastOptimizedAt(new Date());
      setBackendConnected(true);
      setBackendMessage(`Connected to ${API_BASE_URL}`);
    } catch (error) {
      setBackendConnected(false);
      setBackendMessage(`Optimize failed: ${error.message}`);
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="relative h-screen overflow-hidden bg-void text-ink">
      <BackgroundGlow />

      <div className="relative z-10 mx-auto flex h-full max-w-[1450px] flex-col px-4 pb-3 sm:px-5 lg:px-6">
        <TopBar
          onOptimize={handleOptimize}
          isRunning={isRunning}
          lastOptimizedAt={lastOptimizedAt}
          backendConnected={backendConnected}
          modelLoaded={modelLoaded}
          backendMessage={backendMessage}
        />

        <main className="mt-3 grid min-h-0 flex-1 grid-cols-12 grid-rows-12 gap-4">
          <div className="col-span-8 col-start-1 row-span-5 row-start-1 min-h-0">
            <LoadComparisonChart data={chartData} />
          </div>

          <div className="col-span-4 col-start-9 row-span-5 row-start-1 min-h-0">
            <CommandCard
              scenarioOptions={scenarioOptions}
              selectedScenario={selectedScenario}
              onScenarioChange={(value) => {
                setSelectedScenario(value);
                setLastOptimizedAt(null);
              }}
              onOptimize={handleOptimize}
              isRunning={isRunning}
              lastOptimizedAt={lastOptimizedAt}
              backendConnected={backendConnected}
              modelLoaded={modelLoaded}
            />
          </div>

          <div className="col-span-8 col-start-1 row-span-4 row-start-6 min-h-0">
            <StressTimeline data={chartData} />
          </div>

          <div className="col-span-4 col-start-9 row-span-4 row-start-6 grid min-h-0 grid-cols-2 grid-rows-2 gap-3">
            <MetricCard
              label="Peak Overlap Reduced"
              value={`${metrics.peakOverlapReduction.toFixed(1)}%`}
              delta="Weighted load x stress reduction"
              tone="positive"
              icon={Leaf}
            />
            <MetricCard
              label="Jobs Shifted"
              value={`${metrics.jobsShifted}`}
              delta={`Out of ${metrics.totalFlexibleJobs} flexible workloads`}
              tone="accent"
              icon={Shuffle}
            />
            <MetricCard
              label="Grid Friendliness"
              value={`${metrics.gridFriendlinessAfter.toFixed(1)}`}
              delta={`${metrics.gridFriendlinessBefore.toFixed(1)} -> ${metrics.gridFriendlinessAfter.toFixed(1)}`}
              tone="positive"
              icon={Gauge}
            />
            <MetricCard
              label="Peak MW"
              value={`${metrics.peakLoadAfter.toFixed(1)} MW`}
              delta={`${metrics.peakLoadBefore.toFixed(1)} -> ${metrics.peakLoadAfter.toFixed(1)} MW`}
              tone="warning"
              icon={Mountain}
            />
          </div>

          <div className="col-span-12 col-start-1 row-span-3 row-start-10 min-h-0">
            <WorkloadShiftTable rows={workloadRows} />
          </div>
        </main>
      </div>
    </div>
  );
}
