import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { DEMO_PROJECT_ID } from '../demo/demoData';
import { setStoredToken, setDemoMode } from '../api/client';

export interface DemoScene {
  id: string;
  title: string;
  audioFile: string;
  screenCue: string;
  narration: string;
  targetPath: string;
}

export const DEMO_SCENES: DemoScene[] = [
  {
    id: 'scene_01_intro',
    title: 'Scene 1: Introduction & The Core Problem',
    audioFile: '/demo/scene_01_intro.mp3',
    screenCue: 'Landing & Project Dilemma Overview',
    narration:
      'Building technical course projects is challenging. Students and developers often ask themselves: Am I truly meeting the rubric requirements? How many points will my project actually get? And what blockers are standing between me and a passing grade? Meet DevTrack AI: your course-first AI project mentor, designed from the ground up for DataTalksClub Zoomcamps and developer capstone projects.',
    targetPath: '/dashboard',
  },
  {
    id: 'scene_02_login_dashboard',
    title: 'Scene 2: Reviewer Login & Project Dashboard',
    audioFile: '/demo/scene_02_login_dashboard.mp3',
    screenCue: 'Projects Dashboard — 2D Progress Tracking',
    narration:
      'Reviewers can log in instantly with pre-seeded credentials. The Project Dashboard immediately surfaces active assignments with clear deadlines, health indicators, and our signature two-dimensional tracking. Unlike naive tools that conflate tasks with grades, DevTrack AI strictly separates Development Completion from your Expected Course Score.',
    targetPath: '/dashboard',
  },
  {
    id: 'scene_03_scorecard',
    title: 'Scene 3: Official Rubric Scorecard & Safety Invariants',
    audioFile: '/demo/scene_03_scorecard.mp3',
    screenCue: 'Scorecard Panel — 12 Criteria & Estimated vs Verified',
    narration:
      'Inside the project, we see the official AI Dev Tools Zoomcamp 2026 scorecard, spanning twelve criteria and twenty-four maximum points with a ten-point passing threshold. Notice the strict safety invariant: every score is explicitly tagged as Estimated, Verified, or Needs Review. DevTrack AI never masquerades AI guesses as official grades, and when a human reviewer overrides a score, the original AI reasoning remains fully preserved.',
    targetPath: `/projects/${DEMO_PROJECT_ID}?tab=scorecard`,
  },
  {
    id: 'scene_04_analysis_pipeline',
    title: 'Scene 4: Triggering Multi-Agent Analysis & Security Scans',
    audioFile: '/demo/scene_04_analysis_pipeline.mp3',
    screenCue: 'Trigger Analysis Modal — Isolated Scanners & SSRF Guard',
    narration:
      'When we trigger an analysis, background worker agents inspect the public GitHub repository, parse the development diary, and verify live deployments with SSRF protection. Crucially, we never execute untrusted code. Instead, deterministic scanners like Semgrep, Gitleaks, and Bandit run in isolated sandboxes, feeding structured evidence directly to Gemini for rubric matching.',
    targetPath: `/projects/${DEMO_PROJECT_ID}?tab=scorecard&trigger=open`,
  },
  {
    id: 'scene_05_mentor_milestones',
    title: 'Scene 5: AI Mentor Chat & Actionable Milestones',
    audioFile: '/demo/scene_05_mentor_milestones.mp3',
    screenCue: 'Mentor Panel & Milestones View',
    narration:
      "Need to know what to build next? The AI Mentor acts as a personal tutor. Asking 'What is preventing me from reaching twenty points?' produces evidence-backed guidance tied directly to your repository commits and missing rubric deliverables. Milestones are split into official course milestones and practical development subtasks, keeping your engineering plan organized and focused.",
    targetPath: `/projects/${DEMO_PROJECT_ID}?tab=mentor`,
  },
  {
    id: 'scene_06_observability_oncall',
    title: 'Scene 6: Phase 4 On-Call Diagnostics & Observability',
    audioFile: '/demo/scene_06_observability_oncall.mp3',
    screenCue: 'On-Call Diagnostics & Trace Correlation',
    narration:
      "DevTrack AI doesn't stop at code evaluation. With Phase Four Observability, pre-configured Grafana dashboards correlate Prometheus metrics, Loki logs, and Tempo distributed traces via unique trace IDs. Our read-only On-Call Diagnostic Agent can investigate alerts and diagnose system incidents in seconds without mutating production state.",
    targetPath: '/oncall',
  },
  {
    id: 'scene_07_architecture_closing',
    title: 'Scene 7: Architecture, Single-Command Setup & Wrap-Up',
    audioFile: '/demo/scene_07_architecture_closing.mp3',
    screenCue: 'Full-Stack Overview & Single-Command make up',
    narration:
      'Under the hood, DevTrack AI was built using a six-track parallel multi-agent architecture, comprehensive test coverage, and a single-command Docker Compose startup. DevTrack AI: bridging the gap between project idea and a verified, secure, and successful deployment. Thank you for watching!',
    targetPath: '/dashboard',
  },
];

interface DemoTourProps {
  isOpen: boolean;
  onClose: () => void;
}

export function DemoTour({ isOpen, onClose }: DemoTourProps): JSX.Element | null {
  const [currentIdx, setCurrentIdx] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [autoAdvance, setAutoAdvance] = useState(true);
  const [progressPct, setProgressPct] = useState(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const navigate = useNavigate();
  const location = useLocation();

  const currentScene = DEMO_SCENES[currentIdx];

  // Enable demo mode & pre-seed reviewer token when tour is open
  useEffect(() => {
    if (isOpen) {
      setDemoMode(true);
      setStoredToken('demo-bearer-token');
    }
  }, [isOpen]);

  // Navigate to scene target path when scene index changes
  useEffect(() => {
    if (!isOpen) return;
    const target = currentScene.targetPath;
    if (location.pathname + location.search !== target) {
      navigate(target);
    }
  }, [isOpen, currentIdx, currentScene, navigate, location]);

  // Handle scene audio loading and playback
  useEffect(() => {
    if (!isOpen) {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.currentTime = 0;
      }
      setIsPlaying(false);
      return;
    }

    const audio = audioRef.current;
    if (!audio) return;

    audio.src = currentScene.audioFile;
    audio.currentTime = 0;
    setProgressPct(0);

    const playPromise = audio.play();
    if (playPromise !== undefined) {
      playPromise
        .then(() => setIsPlaying(true))
        .catch(() => {
          // Autoplay policy blocked; user must click play
          setIsPlaying(false);
        });
    }
  }, [isOpen, currentIdx, currentScene.audioFile]);

  // Update progress bar
  const onTimeUpdate = () => {
    const audio = audioRef.current;
    if (!audio || !audio.duration) return;
    setProgressPct((audio.currentTime / audio.duration) * 100);
  };

  const nextScene = useCallback(() => {
    if (currentIdx < DEMO_SCENES.length - 1) {
      setCurrentIdx((prev) => prev + 1);
    } else {
      setIsPlaying(false);
    }
  }, [currentIdx]);

  const prevScene = useCallback(() => {
    if (currentIdx > 0) {
      setCurrentIdx((prev) => prev - 1);
    }
  }, [currentIdx]);

  const togglePlay = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (isPlaying) {
      audio.pause();
      setIsPlaying(false);
    } else {
      audio.play().then(() => setIsPlaying(true)).catch(() => {});
    }
  };

  const toggleMute = () => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.muted = !isMuted;
    setIsMuted(!isMuted);
  };

  // Keyboard navigation
  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.code === 'Space') {
        e.preventDefault();
        togglePlay();
      } else if (e.code === 'ArrowRight') {
        e.preventDefault();
        nextScene();
      } else if (e.code === 'ArrowLeft') {
        e.preventDefault();
        prevScene();
      } else if (e.code === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, togglePlay, nextScene, prevScene, onClose]);

  if (!isOpen) return null;

  return (
    <div className="demo-tour-hud" data-testid="demo-tour-hud" role="dialog" aria-label="DevTrack AI Guided Demo">
      <audio
        ref={audioRef}
        onTimeUpdate={onTimeUpdate}
        onEnded={() => {
          if (autoAdvance) nextScene();
          else setIsPlaying(false);
        }}
        muted={isMuted}
      />
      <div className="demo-tour-progress-track">
        <div
          className="demo-tour-progress-bar"
          style={{ width: `${progressPct}%` }}
        />
      </div>

      <div className="demo-tour-body">
        <div className="demo-tour-header">
          <div className="demo-tour-title-group">
            <span className="demo-badge">
              🎬 Scene {currentIdx + 1} of {DEMO_SCENES.length}
            </span>
            <span className="demo-screen-cue">
              🎥 {currentScene.screenCue}
            </span>
          </div>
          <div className="demo-tour-actions-top">
            <label className="demo-auto-label">
              <input
                type="checkbox"
                checked={autoAdvance}
                onChange={(e) => setAutoAdvance(e.target.checked)}
              />
              Auto-advance
            </label>
            <button
              className="btn btn-ghost demo-close-btn"
              onClick={onClose}
              title="Close Demo Tour (Esc)"
              aria-label="Close Tour"
            >
              ✕
            </button>
          </div>
        </div>

        <div className="demo-teleprompter" data-testid="demo-teleprompter">
          <p className="demo-narration-text">"{currentScene.narration}"</p>
        </div>

        <div className="demo-tour-controls">
          <div className="demo-tour-nav-btns">
            <button
              className="btn btn-secondary btn-sm"
              onClick={prevScene}
              disabled={currentIdx === 0}
              data-testid="demo-prev-btn"
            >
              ⏮ Previous
            </button>
            <button
              className="btn btn-primary btn-sm demo-play-btn"
              onClick={togglePlay}
              data-testid="demo-toggle-play-btn"
            >
              {isPlaying ? '⏸ Pause' : '▶ Play'}
            </button>
            <button
              className="btn btn-secondary btn-sm"
              onClick={nextScene}
              disabled={currentIdx === DEMO_SCENES.length - 1}
              data-testid="demo-next-btn"
            >
              ⏭ Next
            </button>
          </div>

          <div className="demo-tour-meta">
            <button
              className="btn btn-ghost btn-sm"
              onClick={toggleMute}
              title={isMuted ? 'Unmute' : 'Mute'}
            >
              {isMuted ? '🔇 Muted' : '🔊 Voiceover'}
            </button>
            <span className="muted small">
              ElevenLabs AI Voice: <strong>Adam</strong> (Turbo v2.5)
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
