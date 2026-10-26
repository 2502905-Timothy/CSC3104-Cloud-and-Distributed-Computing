"use client";

import Image from "next/image";
import {
  useCallback,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Cloud,
  Code2,
  Database,
  GitBranch,
  LockKeyhole,
  Network,
  Play,
  Server,
  ShieldCheck,
  Target,
  TestTube2,
  Users,
  XCircle,
  Zap,
} from "lucide-react";

// Only two text sizes: 12px body and labels; 18px headings.
const BODY_FONT_SIZE = 12;
const TOTAL = 10;

const slideNames = [
  "Overview",
  "The problem",
  "Our solution",
  "Trust mechanism",
  "Architecture",
  "Implementation",
  "Verification",
  "Cloud readiness",
  "Live demo",
  "Next steps",
];

function Panel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`tf-panel rounded-2xl border border-[#25466E] bg-[#10213D]/90 p-5 ${className}`}
    >
      {children}
    </div>
  );
}

function Heading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description?: string;
}) {
  return (
    <div className="mb-5 shrink-0">
      <div className="mb-2 text-[12px] font-bold uppercase tracking-[0.22em] text-[#1BD5FA]">
        {eyebrow}
      </div>
      <h1 className="max-w-[1200px] text-[18px] font-extrabold leading-[1.08] tracking-[-0.045em] text-[#F3F7FF]">
        {title}
      </h1>
      {description && (
        <p className="mt-3 max-w-[1150px] text-[12px] leading-relaxed text-[#B3C9E5]">
          {description}
        </p>
      )}
    </div>
  );
}

function InfoCard({
  icon,
  title,
  description,
  number,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  number?: string;
}) {
  return (
    <Panel className="flex min-h-0 flex-col">
      <div className="mb-4 flex items-center justify-between">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-cyan-300/15 bg-cyan-300/10 text-[#1BD5FA]">{icon}</span>
        {number && (
          <span className="text-[12px] font-bold text-[#7193BD]">
            {number}
          </span>
        )}
      </div>
      <h3 className="text-[18px] font-bold tracking-tight text-white">{title}</h3>
      <p className="mt-2 text-[12px] leading-relaxed text-[#A9C0DD]">
        {description}
      </p>
    </Panel>
  );
}

function TrustGateDiagram({
  compact = false,
}: {
  compact?: boolean;
}) {
  return (
    <div className="w-full">
      <svg
        viewBox="0 0 760 400"
        className={`w-full ${compact ? "max-h-[360px]" : "max-h-[420px]"}`}
        role="img"
        aria-label="Animated federated learning diagram. Three accepted client updates pass through the trust gate into the global model. A malicious update is rejected."
      >
        <defs>
          <linearGradient id="gateGlow" x1="0" x2="1">
            <stop offset="0%" stopColor="#07BDF3" />
            <stop offset="100%" stopColor="#3EE3D0" />
          </linearGradient>
        </defs>

        {[
          { name: "A", y: 75 },
          { name: "B", y: 155 },
          { name: "C", y: 235 },
        ].map((client) => (
          <g key={client.name}>
            <circle
              cx="90"
              cy={client.y}
              r="25"
              fill="#132849"
              stroke="#426B9C"
              strokeWidth="2"
            />
            <text
              x="90"
              y={client.y + 6}
              textAnchor="middle"
              fill="#F3F7FF"
              fontSize="12"
              fontWeight="700"
            >
              {client.name}
            </text>
            <path
              d={`M 115 ${client.y} H 420`}
              stroke="#365C83"
              strokeWidth="2"
              fill="none"
            />
          </g>
        ))}

        <circle
          cx="90"
          cy="315"
          r="25"
          fill="#132849"
          stroke="#FB7185"
          strokeWidth="2"
        />
        <text
          x="90"
          y="321"
          textAnchor="middle"
          fill="white"
          fontSize="12"
          fontWeight="700"
        >
          M
        </text>

        <path
          d="M115 315 H420"
          stroke="#FB7185"
          strokeWidth="2"
          strokeDasharray="6 7"
          fill="none"
        />

        <rect
          x="420"
          y="38"
          width="29"
          height="302"
          rx="14"
          fill="#0A2840"
          stroke="url(#gateGlow)"
          strokeWidth="2.5"
        />
        <text
          x="439"
          y="190"
          textAnchor="middle"
          transform="rotate(-90 439 190)"
          fill="#45E3F4"
          fontSize="12"
          fontWeight="700"
        >
          TRUST GATE
        </text>

        <path
          id="acceptedA"
          d="M449 75 C535 75 570 195 645 195"
          stroke="#19C8E6"
          strokeWidth="2.5"
          fill="none"
        />
        <path
          id="acceptedB"
          d="M449 155 C535 155 570 195 645 195"
          stroke="#19C8E6"
          strokeWidth="2.5"
          fill="none"
        />
        <path
          id="acceptedC"
          d="M449 235 C535 235 570 195 645 195"
          stroke="#19C8E6"
          strokeWidth="2.5"
          fill="none"
        />

        <circle
          cx="688"
          cy="195"
          r="43"
          fill="#102A4C"
          stroke="#18D9F5"
          strokeWidth="2.5"
        />
        <text
          x="688"
          y="189"
          textAnchor="middle"
          fill="white"
          fontSize="12"
          fontWeight="700"
        >
          GLOBAL
        </text>
        <text
          x="688"
          y="208"
          textAnchor="middle"
          fill="white"
          fontSize="12"
          fontWeight="700"
        >
          MODEL
        </text>

        {[
          { id: "acceptedA", y: 75, delay: "0s" },
          { id: "acceptedB", y: 155, delay: "0.7s" },
          { id: "acceptedC", y: 235, delay: "1.4s" },
        ].map((item) => (
          <circle r="6" fill="#53E5B0" key={item.id} className="tf-particle">
            <animateMotion
              dur="4.5s"
              repeatCount="indefinite"
              begin={item.delay}
              path={`M115 ${item.y} H449 C535 ${item.y} 570 195 645 195`}
            />
          </circle>
        ))}

        <circle r="7" fill="#FB7185" className="tf-particle">
          <animateMotion
            path="M135 315 H405"
            dur="3.5s"
            repeatCount="indefinite"
          />
        </circle>

        <text
          x="463"
          y="325"
          fill="#FB7185"
          fontSize="12"
          fontWeight="700"
        >
          ×
        </text>

        <circle cx="240" cy="374" r="5" fill="#53E5B0" />
        <text x="254" y="379" fill="#AAC2DF" fontSize="12">
          Accepted updates
        </text>

        <circle cx="430" cy="374" r="5" fill="#FB7185" />
        <text x="444" y="379" fill="#AAC2DF" fontSize="12">
          Rejected update
        </text>
      </svg>
    </div>
  );
}

function ArchitectureDiagram() {
  return (
    <div className="grid w-full gap-2 rounded-2xl border border-[#25496F] bg-[#0D1E39] p-3 text-center text-white">
      <div className="grid grid-cols-3 gap-2">
        {["A", "B", "C"].map((client) => (
          <div
            key={client}
            className="rounded-lg border border-[#345D88] bg-[#142D50] px-2 py-2.5"
          >
            <div className="text-[12px] font-bold">
              Client {client}
            </div>
            <div className="mt-1 text-[12px] text-[#9FC2E3]">
              Local training
            </div>
          </div>
        ))}
      </div>

      <div className="text-[12px] font-semibold text-[#18D4FF]">
        ↓ Model updates transmitted over network ↓
      </div>

      <div className="rounded-lg border border-[#18CFFF] bg-[#103657] px-3 py-2.5">
        <div className="flex items-center justify-center gap-2 text-[12px] font-bold">
          <Server size={17} className="text-[#1BD5FA]" />
          FastAPI Coordinator
        </div>
        <div className="mt-1 text-[12px] text-[#B5D9F4]">
          Round orchestration · Update collection
        </div>
      </div>

      <div className="text-[12px] text-[#18D4FF]">↓</div>

      <div className="rounded-lg border border-[#20D4E9] bg-[#123A52] px-3 py-2.5">
        <div className="flex items-center justify-center gap-2 text-[12px] font-bold">
          <ShieldCheck size={17} className="text-[#45E3F4]" />
          Trust Gate + Trust-Aware Aggregator
        </div>
        <div className="mt-1 text-[12px] text-[#B5D9F4]">
          Validate · Assess reliability · Weight accepted updates
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 text-[12px]">
        <div className="rounded-lg border border-[#FB7185]/50 bg-[#381D31] p-2.5">
          <div className="flex items-center justify-center gap-1 font-bold text-[#FB7185]">
            <XCircle size={15} /> Rejected
          </div>
          <div className="mt-1 text-[#F5B4BF]">
            Suspicious update excluded
          </div>
        </div>

        <div className="rounded-lg border border-[#42DDB0]/50 bg-[#123B49] p-2.5">
          <div className="flex items-center justify-center gap-1 font-bold text-[#5EE2B5]">
            <CheckCircle2 size={15} /> Global Model
          </div>
          <div className="mt-1 text-[#B9ECDD]">
            Accepted updates aggregated
          </div>
        </div>

        <div className="rounded-lg border border-[#5488BE] bg-[#142D50] p-2.5">
          <div className="flex items-center justify-center gap-1 font-bold text-[#A7D6FF]">
            <Database size={15} /> SQLite
          </div>
          <div className="mt-1 text-[#A9C9E3]">
            Persistent trust history
          </div>
        </div>
      </div>

      <div className="border-t border-[#25496F] pt-2 text-[12px] text-[#9FC2E3]">
        ↺ Updated global model shared with clients for the next round
      </div>
    </div>
  );
}

function SlideContent({ index }: { index: number }) {
  switch (index) {
    case 0:
      return (
        <div className="grid h-full items-center gap-6 lg:grid-cols-[0.9fr_1.1fr]">
          <div>
            <div className="mb-5 text-[12px] font-bold uppercase tracking-[0.25em] text-[#1BD5FA]">
              Trust-aware federated learning
            </div>
            <h1 className="text-[18px] font-black leading-none tracking-[-0.075em] text-white">
              Trust<span className="text-[#19C9F4]">Fed</span>
            </h1>
            <p className="mt-6 max-w-[570px] text-[12px] leading-relaxed text-[#C1D4EA]">
              Decentralised scam-message detection without
              blindly trusting every client update.
            </p>
            <div className="mt-7 flex flex-wrap gap-2">
              {[
                "Federated learning",
                "Trust-aware aggregation",
                "Cloud-native design",
              ].map((tag) => (
                <span
                  key={tag}
                  className="rounded-full border border-[#20547D] bg-[#0E2A46] px-3 py-1.5 text-[12px] font-semibold text-[#8FE9FF]"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>

          <div className="min-w-0 rounded-2xl border border-[#244D77] bg-[#0A1B34]/70 p-3">
            <TrustGateDiagram compact />
          </div>
        </div>
      );

    case 1:
      return (
        <>
          <Heading
            eyebrow="01 / The problem"
            title="Learning together creates a new trust problem."
            description="Federated learning avoids centralising raw training data, but the coordinator still needs to decide which client updates deserve influence."
          />
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <InfoCard
              number="01"
              icon={<LockKeyhole size={28} />}
              title="Centralised data"
              description="Traditional approaches may require collecting sensitive messages in one place."
            />
            <InfoCard
              number="02"
              icon={<Network size={28} />}
              title="Different client data"
              description="Clients may have unequal datasets and different scam-message patterns."
            />
            <InfoCard
              number="03"
              icon={<ShieldCheck size={28} />}
              title="Untrusted updates"
              description="A faulty or malicious participant can submit a harmful model update."
            />
          </div>
          <p className="mt-5 border-l-2 border-[#1BD5FA] pl-4 text-[12px] text-[#C4D8F0]">
            The challenge: collaborate without automatically trusting every participant.
          </p>
        </>
      );

    case 2:
      return (
        <>
          <Heading
            eyebrow="02 / Our solution"
            title="Federated learning, with accountability."
            description="TrustFed adds a trust-aware decision layer before client updates are combined into the global model."
          />
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <InfoCard
              icon={<Users size={28} />}
              title="Train locally"
              description="Clients train on their own message data and submit model updates."
              number="01"
            />
            <InfoCard
              icon={<ShieldCheck size={28} />}
              title="Evaluate updates"
              description="The coordinator assesses incoming updates using validation and trust information."
              number="02"
            />
            <InfoCard
              icon={<GitBranch size={28} />}
              title="Aggregate selectively"
              description="Accepted updates contribute to the global model; suspicious ones can be rejected."
              number="03"
            />
          </div>
          <Panel className="mt-4 border-[#1BD5FA]/40">
            <p className="text-center text-[12px] font-semibold text-[#AEEBFC]">
              Local learning → Trust evaluation → Selective aggregation → Updated global model
            </p>
          </Panel>
        </>
      );

    case 3:
      return (
        <>
          <Heading
            eyebrow="03 / Trust mechanism"
            title="Not every update gets through."
            description="The trust gate separates accepted model updates from an intentionally adversarial update."
          />
          <div className="mx-auto w-full max-w-[1080px]">
            <TrustGateDiagram />
          </div>
        </>
      );

    case 4:
      return (
        <>
          <Heading
            eyebrow="04 / Architecture"
            title="Distributed by design."
            description="Container-ready clients, a FastAPI coordinator, trust-aware aggregation and persisted trust decisions."
          />
          <div className="grid min-h-0 gap-4 lg:grid-cols-[1.25fr_0.75fr]">
            <ArchitectureDiagram />

            <div className="grid gap-3">
              <InfoCard
                icon={<Code2 size={23} />}
                title="Services"
                description="Python and FastAPI components with Docker containerisation work."
              />
              <InfoCard
                icon={<Database size={23} />}
                title="Persistence"
                description="SQLite trust decisions remain available after coordinator restarts."
              />
              <InfoCard
                icon={<Cloud size={23} />}
                title="Deployment status"
                description="Kubernetes configuration exists; cluster deployment is not yet verified."
              />
            </div>
          </div>
        </>
      );

    case 5:
      return (
        <>
          <Heading
            eyebrow="05 / Implementation"
            title="From design to a working system."
            description="The current implementation connects training clients, coordinator APIs, trust evaluation and persistent records."
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <InfoCard
              icon={<Server size={26} />}
              title="FastAPI coordinator"
              description="Provides health, client information and federated-round endpoints."
            />
            <InfoCard
              icon={<ShieldCheck size={26} />}
              title="TrustFedAdapter"
              description="Implements trust-aware update handling and malicious-update rejection."
            />
            <InfoCard
              icon={<Database size={26} />}
              title="Persistent records"
              description="SQLite stores trust-related history across coordinator restarts."
            />
            <InfoCard
              icon={<TestTube2 size={26} />}
              title="Automated tests"
              description="Unit and integration checks exercise the current implementation."
            />
          </div>
        </>
      );

    case 6:
      return (
        <>
          <Heading
            eyebrow="06 / Verified progress"
            title="Working software. Measurable evidence."
            description="Results from local development and controlled testing — not claims of production readiness."
          />
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              ["45", "Automated tests passed"],
              ["3", "Client updates accepted"],
              ["1", "Malicious update rejected"],
              ["2", "Local training rounds"],
            ].map(([value, label]) => (
              <Panel key={label} className="text-center">
                <div className="text-[18px] font-black text-[#1BD5FA]">
                  {value}
                </div>
                <div className="mt-1 text-[12px] text-[#C0D4EB]">
                  {label}
                </div>
              </Panel>
            ))}
          </div>

          <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Panel>
              <div className="flex items-center gap-2 font-bold text-[#63E8B8]">
                <CheckCircle2 size={20} />
                Confirmed locally
              </div>
              <p className="mt-2 text-[12px] text-[#AFC5E1]">
                Coordinator endpoints respond, adversarial rejection works,
                and trust history persists through restart.
              </p>
            </Panel>
            <Panel>
              <div className="flex items-center gap-2 font-bold text-[#F5C879]">
                <Target size={20} />
                Still to establish
              </div>
              <p className="mt-2 text-[12px] text-[#AFC5E1]">
                Generalisation on held-out data, rigorous FedAvg comparison
                and verified cloud deployment.
              </p>
            </Panel>
          </div>
        </>
      );

    case 7:
      return (
        <>
          <Heading
            eyebrow="07 / Cloud-native readiness"
            title="Built to evolve beyond one machine."
            description="TrustFed separates client training, coordination and aggregation so they can be deployed and managed as distinct services."
          />
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <InfoCard
              icon={<Code2 size={28} />}
              title="Containerisation"
              description="Docker-related infrastructure work supports packaging the components."
            />
            <InfoCard
              icon={<Network size={28} />}
              title="Distributed communication"
              description="Clients interact with coordinator APIs over the network."
            />
            <InfoCard
              icon={<Cloud size={28} />}
              title="Kubernetes direction"
              description="Deployment configuration is present, with cluster validation remaining."
            />
          </div>
          <Panel className="mt-4">
            <p className="text-[12px] text-[#B9D4F0]">
              <strong className="text-white">Current status:</strong>{" "}
              Local system functionality has been demonstrated.
              Kubernetes cluster deployment has not yet been confirmed.
            </p>
          </Panel>
        </>
      );

    case 8:
      return (
        <>
          <Heading
            eyebrow="08 / Live demonstration"
            title="See TrustFed in action."
            description="We demonstrate the system's decisions, not just its design."
          />
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
            {[
              {
                number: "01",
                title: "Train",
                description:
                  "Run clients and complete a federated training round.",
                icon: <Play size={25} />,
              },
              {
                number: "02",
                title: "Attack",
                description:
                  "Submit an intentionally adversarial model update.",
                icon: <Zap size={25} />,
              },
              {
                number: "03",
                title: "Verify",
                description:
                  "Inspect accepted and rejected updates, then verify persisted trust history.",
                icon: <CheckCircle2 size={25} />,
              },
            ].map((step) => (
              <Panel key={step.number}>
                <div className="flex items-center justify-between">
                  <span className="text-[#1BD5FA]">
                    {step.icon}
                  </span>
                  <span className="text-[12px] font-bold text-[#638DBB]">
                    {step.number}
                  </span>
                </div>
                <h3 className="mt-4 text-[18px] font-bold text-white">
                  {step.title}
                </h3>
                <p className="mt-2 text-[12px] leading-relaxed text-[#AFC5E1]">
                  {step.description}
                </p>
              </Panel>
            ))}
          </div>
          <p className="mt-5 text-[12px] text-[#8EACCE]">
            Demonstration uses a controlled local setup and synthetic test inputs.
          </p>
        </>
      );

    case 9:
      return (
        <>
          <Heading
            eyebrow="09 / Next steps"
            title="From verified prototype to robust evaluation."
            description="Our remaining work focuses on stronger evidence, realistic client diversity and deployment validation."
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <InfoCard
              number="01"
              icon={<BarChart3 size={27} />}
              title="Benchmark aggregation"
              description="Compare FedAvg, Krum and TrustFed using consistent datasets and metrics."
            />
            <InfoCard
              number="02"
              icon={<Users size={27} />}
              title="Stress-test clients"
              description="Evaluate non-IID data, client dropouts and different malicious-client proportions."
            />
            <InfoCard
              number="03"
              icon={<Cloud size={27} />}
              title="Validate deployment"
              description="Run and verify containerised components on the intended Kubernetes infrastructure."
            />
            <InfoCard
              number="04"
              icon={<Target size={27} />}
              title="Measure trade-offs"
              description="Report F1, precision, recall, runtime and communication overhead."
            />
          </div>
          <p className="mt-5 text-[12px] font-semibold text-[#6CE5F8]">
            TrustFed: decentralised learning with accountable updates.
          </p>
        </>
      );

    default:
      return null;
  }
}

export default function Home() {
  const [slide, setSlide] = useState(0);
  const [logoError, setLogoError] = useState(false);

  const goTo = useCallback((next: number) => {
    setSlide(Math.max(0, Math.min(TOTAL - 1, next)));
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (event.altKey || event.ctrlKey || event.metaKey ||
          target?.isContentEditable || target?.closest("input, textarea, select, button")) return;
      if (
        event.key === "ArrowRight" ||
        event.key === "PageDown"
      ) {
        event.preventDefault();
        setSlide((current) =>
          Math.min(TOTAL - 1, current + 1)
        );
      }

      if (
        event.key === "ArrowLeft" ||
        event.key === "PageUp"
      ) {
        event.preventDefault();
        setSlide((current) =>
          Math.max(0, current - 1)
        );
      }

      if (event.key === "Home") {
        event.preventDefault();
        setSlide(0);
      }

      if (event.key === "End") {
        event.preventDefault();
        setSlide(TOTAL - 1);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () =>
      window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <main
      className="trustfed relative grid h-dvh min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden bg-[#071329] text-white"
      style={{
        fontSize: BODY_FONT_SIZE,
        lineHeight: 1.65,
        background:
          "radial-gradient(ellipse at 95% 20%, #083454 0%, transparent 48%), linear-gradient(135deg, #081124 0%, #07172D 60%, #061329 100%)",
      }}
    >
      {/* Header */}
      <header className="relative z-10 shrink-0 border-b border-[#294263]/70">
        <div className="mx-auto flex h-[64px] max-w-[1440px] items-center justify-between px-6 md:px-12">
          <button
            type="button"
            onClick={() => goTo(0)}
            aria-label="Go to first slide"
            className="flex items-center gap-3"
          >
            {!logoError ? (
              <Image
                src="/trustfed-logo.png"
                alt="TrustFed logo"
                width={66}
                height={48}
                className="h-12 w-[66px] object-contain"
                priority
                onError={() => setLogoError(true)}
              />
            ) : (
              <ShieldCheck
                size={34}
                className="text-[#16C9F4]"
              />
            )}

            <span className="text-[18px] font-extrabold tracking-tight">
              Trust<span className="text-[#1BCBF4]">Fed</span>
            </span>
          </button>

          <span className="text-[12px] font-bold uppercase tracking-[0.25em] text-[#92BCE5] sm:text-[12px]">
            CSC3104 / Group 13
          </span>
        </div>

        <div className="h-[3px] bg-[#183555]">
          <div
            className="h-full bg-gradient-to-r from-[#147DFF] to-[#19D9F4] transition-[width] duration-300"
            style={{
              width: `${((slide + 1) / TOTAL) * 100}%`,
            }}
          />
        </div>
      </header>

      {/* Slide viewport */}
      <section key={slide} aria-label={`${slideNames[slide]} — slide ${slide + 1} of ${TOTAL}`} className="tf-viewport relative z-0 min-h-0 overflow-y-auto overflow-x-hidden">
        <div className="mx-auto flex min-h-full w-full max-w-[1440px] flex-col px-5 py-6 md:px-12">
          <div
            key={slide}
            className="my-auto w-full shrink-0 animate-[fadeIn_350ms_ease-out]"
          >
            <SlideContent index={slide} />
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative z-10 shrink-0 border-t border-[#294263]/70 bg-[#081329]/95">
        <div className="mx-auto flex h-[60px] max-w-[1440px] items-center justify-between gap-4 px-6 md:px-12">
          <div className="flex items-center gap-4">
            <span className="text-[18px] font-extrabold tabular-nums">
              {String(slide + 1).padStart(2, "0")}
              <span className="ml-1 text-[12px] font-normal text-[#759FCB]">
                / {String(TOTAL).padStart(2, "0")}
              </span>
            </span>
            <span className="hidden text-[12px] font-bold uppercase tracking-[0.16em] text-[#91B7E0] sm:block">
              {slideNames[slide]}
            </span>
          </div>

          <nav aria-label="Choose slide" className="hidden items-center gap-2 lg:flex">
            {slideNames.map((name, i) => (
              <button key={name} type="button" onClick={() => goTo(i)}
                aria-label={`Slide ${i + 1}: ${name}`} aria-current={slide === i ? "step" : undefined}
                title={name} className="flex h-8 w-5 items-center justify-center">
                <span className={`h-1.5 rounded-full transition-all ${slide === i ? "w-5 bg-cyan-300" : "w-1.5 bg-slate-600"}`} />
              </button>
            ))}
          </nav>
          <div className="flex items-center gap-3">

            <button
              type="button"
              onClick={() => goTo(slide - 1)}
              disabled={slide === 0}
              aria-label="Previous slide"
              className="flex h-11 w-11 items-center justify-center rounded-xl border border-[#29466A] bg-[#10203B] text-white transition hover:bg-[#1A355A] disabled:cursor-not-allowed disabled:opacity-30"
            >
              <ArrowLeft size={22} />
            </button>

            <button
              type="button"
              onClick={() => goTo(slide + 1)}
              disabled={slide === TOTAL - 1}
              aria-label="Next slide"
              className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#18CFF2] text-[#061329] transition hover:bg-[#67E8F9] disabled:cursor-not-allowed disabled:opacity-30"
            >
              <ArrowRight size={22} />
            </button>
          </div>
        </div>
      </footer>

      <style jsx global>{`
        html,
        body {
          margin: 0;
          height: 100%;
          overflow: hidden;
        }

        .trustfed h1, .trustfed h2, .trustfed h3 { font-size: 18px; }
        .trustfed p { font-size: 12px; line-height: 1.8; }
        .trustfed .tf-panel {
          background: linear-gradient(145deg, rgba(22, 46, 76, .86), rgba(12, 29, 52, .94));
          box-shadow: inset 0 1px 0 rgba(164, 222, 255, .05), 0 12px 32px rgba(0, 0, 0, .12);
        }
        .trustfed button:focus-visible { outline: 2px solid #67e8f9; outline-offset: 4px; }
        .tf-viewport { scrollbar-width: thin; scrollbar-color: #315574 transparent; }
        .tf-particle { filter: drop-shadow(0 0 4px currentColor); }
        @media (prefers-reduced-motion: reduce) {
          .trustfed *, .trustfed *::before, .trustfed *::after {
            animation: none !important; transition: none !important;
          }
          .tf-particle { display: none; }
        }
        @keyframes fadeIn {
          from {
            opacity: 0;
            transform: translateY(8px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </main>
  );
}
