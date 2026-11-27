import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  Activity,
  Box,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Cloud,
  Code2,
  Copy,
  Database,
  FileSpreadsheet,
  FlaskConical,
  Layers3,
  LayoutDashboard,
  Loader2,
  LogOut,
  Menu,
  Play,
  Plus,
  RefreshCw,
  Rocket,
  Search,
  Server,
  Settings2,
  ShieldCheck,
  Sparkles,
  Triangle,
  UploadCloud,
  WandSparkles,
  X,
  Zap,
} from "lucide-react";
import {
  api,
  config,
  sampleFile,
  signIn,
  signedIn,
  signOut,
  upload,
  type Dataset,
  type Deployment,
  type DeployResult,
  type Job,
  type Page,
  type Profile,
} from "./api";

const fmt = (n: number) => new Intl.NumberFormat("vi-VN").format(n);
const date = (n?: number) =>
  n
    ? new Date(n * 1000).toLocaleString("vi-VN", {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
const bytes = (n = 0) =>
  n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${(n / 1000).toFixed(1)} KB`;
const statusLabel: Record<string, string> = {
  QUEUED: "Đang chờ",
  TRAINING: "Đang huấn luyện",
  COMPLETED: "Hoàn thành",
  FAILED: "Thất bại",
  CANCELLED: "Đã hủy",
  READY: "Sẵn sàng",
  UPLOADING: "Chờ upload",
  ACTIVE: "Hoạt động",
  REVOKED: "Đã thu hồi",
};
function Badge({ status }: { status: string }) {
  return (
    <span className={`badge status-${status.toLowerCase()}`}>
      <span />
      {statusLabel[status] || status}
    </span>
  );
}
function Logo({ light = false }: { light?: boolean }) {
  return (
    <span className={`logo ${light ? "light" : ""}`}>
      <span className="logo-symbol">
        <Triangle size={21} />
      </span>
      stratus<span className="logo-dot">.</span>
    </span>
  );
}
function Button({
  children,
  onClick,
  kind = "",
  disabled = false,
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  kind?: string;
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      className={`btn ${kind}`}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}
function ErrorBox({ message }: { message: string }) {
  return message ? (
    <div className="error" role="alert">
      <CircleHelp size={18} />
      <span>{message}</span>
    </div>
  ) : null;
}
function Loading() {
  return (
    <div className="loading">
      <Loader2 className="spin" size={23} />
      Đang tải dữ liệu…
    </div>
  );
}
function Empty({
  icon,
  headline,
  detail,
  action,
}: {
  icon: ReactNode;
  headline: string;
  detail: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon}</div>
      <h3>{headline}</h3>
      <p>{detail}</p>
      {action}
    </div>
  );
}
function usePath() {
  const [path, setPath] = useState(location.pathname);
  useEffect(() => {
    const update = () => setPath(location.pathname);
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, []);
  const go = (next: string) => {
    history.pushState({}, "", next);
    setPath(next);
    window.scrollTo(0, 0);
  };
  return [path, go] as const;
}
function useList<T>(path: string) {
  const [items, setItems] = useState<T[]>([]),
    [cursor, setCursor] = useState<string | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const page = await api<Page<T>>(path);
      setItems(page.items);
      setCursor(page.cursor);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  const more = async () => {
    try {
      const page = await api<Page<T>>(
        `${path}?cursor=${encodeURIComponent(cursor!)}`,
      );
      setItems((old) => [...old, ...page.items]);
      setCursor(page.cursor);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return { items, cursor, loading, error, refresh, more };
}
function CopyButton({
  text,
  label = "Sao chép",
}: {
  text: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      kind="subtle small"
      onClick={() => {
        void navigator.clipboard
          .writeText(text)
          .then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
          })
          .catch(() => setCopied(false));
      }}
    >
      {copied ? <Check size={15} /> : <Copy size={15} />}{" "}
      {copied ? "Đã sao chép" : label}
    </Button>
  );
}

export default function App({ authError }: { authError: string }) {
  const [path, go] = usePath(),
    [menu, setMenu] = useState(false),
    [error, setError] = useState(authError),
    [keys, setKeys] = useState<Record<string, string>>({});
  const start = () => {
    if (signedIn()) go("/app");
    else void signIn().catch((e) => setError(e.message));
  };
  const keepKey = (id: string, key: string) =>
    setKeys((old) => ({ ...old, [id]: key }));
  if (!path.startsWith("/app")) return <Landing start={start} error={error} />;
  if (!signedIn())
    return (
      <div className="auth-screen">
        <Logo />
        <ShieldCheck size={44} />
        <h1>Workspace của bạn</h1>
        <p>Đăng nhập để quản lý dữ liệu, model và endpoint.</p>
        <ErrorBox message={error} />
        <Button onClick={start}>Đăng nhập với Cognito</Button>
        <button className="text-button" onClick={() => go("/")}>
          Về trang chủ
        </button>
      </div>
    );
  const active = path.includes("/datasets")
    ? "datasets"
    : path.includes("/jobs")
      ? "jobs"
      : path.includes("/endpoints")
        ? "endpoints"
        : path.includes("/settings")
          ? "settings"
          : path.includes("/new")
            ? "new"
            : "overview";
  const nav = [
    { id: "overview", path: "/app", label: "Tổng quan", icon: LayoutDashboard },
    { id: "datasets", path: "/app/datasets", label: "Dữ liệu", icon: Database },
    { id: "jobs", path: "/app/jobs", label: "Thí nghiệm", icon: FlaskConical },
    { id: "endpoints", path: "/app/endpoints", label: "Endpoints", icon: Box },
  ];
  const navigate = (next: string) => {
    go(next);
    setMenu(false);
  };
  return (
    <div className="shell">
      {menu && (
        <button
          className="sidebar-overlay"
          aria-label="Đóng menu"
          onClick={() => setMenu(false)}
        />
      )}
      <aside className={`sidebar ${menu ? "open" : ""}`}>
        <button className="brand-button" onClick={() => navigate("/")}>
          <Logo light />
        </button>
        <div className="workspace-switch">
          <span className="workspace-icon">S</span>
          <div>
            <strong>ML Workspace</strong>
            <small>
              {config.local ? "Local development" : "AWS workspace"}
            </small>
          </div>
          <ChevronDown size={15} />
        </div>
        <span className="nav-caption">WORKSPACE</span>
        <nav>
          {nav.map((item) => (
            <button
              key={item.id}
              className={active === item.id ? "selected" : ""}
              onClick={() => navigate(item.path)}
            >
              <item.icon size={19} />
              {item.label}
              {active === item.id && <span className="nav-active" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="cloud-note">
            <Cloud size={22} />
            <strong>Compute theo nhu cầu</strong>
            <p>Worker tự khởi động khi có job và về 0 khi rảnh.</p>
            <span>EC2 AUTO SCALING</span>
          </div>
          <button
            className={`settings-link ${active === "settings" ? "selected" : ""}`}
            onClick={() => navigate("/app/settings")}
          >
            <Settings2 size={19} />
            Kết nối & hạ tầng
          </button>
          <div className="user-row">
            <span className="avatar">ML</span>
            <div>
              <strong>
                {config.local ? "Local workspace" : "My workspace"}
              </strong>
              <small>{config.region}</small>
            </div>
            <button aria-label="Đăng xuất" onClick={signOut}>
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="app-topbar">
          <div>
            <button
              className="mobile-menu"
              aria-label="Mở menu"
              onClick={() => setMenu(true)}
            >
              <Menu size={20} />
            </button>
            <span className="muted">Workspace</span>
            <ChevronRight size={14} />
            <strong>
              {active === "new"
                ? "Thí nghiệm mới"
                : nav.find((n) => n.id === active)?.label || "Cài đặt"}
            </strong>
          </div>
          <div>
            <span className="environment">
              <Cloud size={14} />
              {config.local ? "LOCAL" : "AWS"}
              <span className="region">{config.region}</span>
            </span>
            <button
              className="icon-button"
              aria-label="Trợ giúp"
              onClick={() => navigate("/app/settings")}
            >
              <CircleHelp size={19} />
            </button>
          </div>
        </header>
        <main className="workspace-main" key={path}>
          {active === "overview" && <Overview go={navigate} />}
          {active === "datasets" && <Datasets go={navigate} />}
          {active === "new" && <NewExperiment go={navigate} />}
          {active === "jobs" &&
            (path.split("/").length > 3 ? (
              <JobDetail
                id={path.split("/")[3]}
                go={navigate}
                keepKey={keepKey}
              />
            ) : (
              <Jobs go={navigate} />
            ))}
          {active === "endpoints" && (
            <Endpoints keys={keys} keepKey={keepKey} />
          )}
          {active === "settings" && <Settings />}
        </main>
        <footer className="app-footer">
          <span>Stratus Cloud AutoML</span>
          <span>Built on AWS · Powered by AutoGluon</span>
        </footer>
      </div>
    </div>
  );
}

function Landing({ start, error }: { start: () => void; error: string }) {
  return (
    <div className="landing">
      <nav className="landing-nav">
        <Logo light />
        <div className="landing-links">
          <a href="#workflow">Quy trình</a>
          <a href="#platform">Nền tảng</a>
          <button onClick={start}>Đăng nhập</button>
        </div>
        <Button onClick={start}>Mở workspace</Button>
      </nav>
      <section className="hero">
        <div className="hero-copy">
          <div className="eyebrow">
            <span className="tiny-cloud">
              <Cloud size={15} />
            </span>{" "}
            YOUR DATA. YOUR NEXT MOVE.
          </div>
          <h1>
            Từ dữ liệu.
            <br />
            Đến <span>điều tiếp theo.</span>
          </h1>
          <p>
            Biến bảng dữ liệu thành mô hình dự đoán.
            <br />
            Một workspace để chuẩn bị dữ liệu, huấn luyện và đưa AI vào ứng dụng
            của bạn.
          </p>
          <div className="hero-actions">
            <Button onClick={start}>
              <Sparkles size={18} />
              Tạo mô hình đầu tiên
            </Button>
            <a href="#workflow" className="hero-link">
              Khám phá quy trình
            </a>
          </div>
          <ErrorBox message={error} />
          <div className="hero-proof">
            <span>
              <Check size={15} />
              Không cần viết pipeline ML
            </span>
            <span>
              <Check size={15} />
              Hạ tầng AWS của bạn
            </span>
          </div>
        </div>
        <div
          className="hero-visual"
          aria-label="Minh họa pipeline từ CSV đến model và API"
        >
          <div className="visual-grid" />
          <div className="visual-top">
            <span>
              <span className="pulse-dot" /> MODEL PIPELINE
            </span>
            <span>Minh họa</span>
          </div>
          <div className="pipeline-input">
            <span className="pipeline-icon">
              <FileSpreadsheet size={23} />
            </span>
            <div>
              <strong>customer-churn.csv</strong>
              <small>Dữ liệu khách hàng</small>
            </div>
            <CheckCircle2 size={18} />
          </div>
          <div className="pipeline-wire wire-a" />
          <div className="model-core">
            <div className="core-orbit orbit-one" />
            <div className="core-orbit orbit-two" />
            <div className="core-face">
              <Layers3 size={38} />
              <span>AUTOGLUON</span>
            </div>
            <span className="float-tag tag-a">
              <WandSparkles size={13} />
              Preprocess
            </span>
            <span className="float-tag tag-b">
              <Server size={13} />
              Auto Scaling
            </span>
          </div>
          <div className="pipeline-wire wire-b" />
          <div className="prediction-terminal">
            <div>
              <span className="terminal-dots">
                <i />
                <i />
                <i />
              </span>
              <span>prediction.json</span>
              <Code2 size={14} />
            </div>
            <pre>
              <span className="code-gray">{"// Model inference"}</span>
              {"\n{\n  "}
              <span className="code-green">"predictions"</span>
              {": ["}
              <span className="code-orange">"yes", "no"</span>
              {"]\n}"}
            </pre>
          </div>
          <div className="visual-bottom">
            <span>CSV</span>
            <i />
            <span>MODEL</span>
            <i />
            <span>API</span>
          </div>
        </div>
      </section>
      <div className="service-strip">
        <span>ĐƯỢC XÂY DỰNG TRÊN</span>
        {[
          "Amazon S3",
          "EC2 Auto Scaling",
          "DynamoDB",
          "Amazon ECR",
          "AWS Lambda",
        ].map((s, i) => (
          <span key={s}>
            {[<Database />, <Server />, <Layers3 />, <Box />, <Zap />][i]}
            {s}
          </span>
        ))}
      </div>
      <section id="workflow" className="workflow-section">
        <div className="section-heading">
          <div>
            <span className="eyebrow">LESS SETUP. MORE DISCOVERY.</span>
            <h2>
              Một luồng làm việc.
              <br />
              Từ ý tưởng đến dự đoán.
            </h2>
          </div>
          <p>
            Giữ sự tập trung vào dữ liệu và bài toán.
            <br />
            Stratus kết nối các bước còn lại.
          </p>
        </div>
        <div className="workflow-grid">
          {[
            {
              icon: UploadCloud,
              title: "Đưa dữ liệu vào",
              text: "Upload CSV, khám phá cấu trúc, giá trị thiếu và dữ liệu trùng lặp.",
              tag: "S3 DATASETS",
            },
            {
              icon: WandSparkles,
              title: "Chuẩn bị & huấn luyện",
              text: "Chọn mục tiêu, làm sạch dữ liệu và để AutoGluon học trên EC2.",
              tag: "SQS + AUTO SCALING",
            },
            {
              icon: Rocket,
              title: "Đưa model vào thực tế",
              text: "Triển khai endpoint, tạo API key riêng và thử dự đoán ngay.",
              tag: "ECR + LAMBDA",
            },
          ].map((item) => (
            <article key={item.title}>
              <item.icon size={28} />
              <h3>{item.title}</h3>
              <p>{item.text}</p>
              <span>{item.tag}</span>
            </article>
          ))}
        </div>
      </section>
      <section id="platform" className="platform-section">
        <div>
          <span className="eyebrow">A WORKSPACE THAT GROWS WITH YOU</span>
          <h2>
            Bắt đầu nhỏ.
            <br />
            Sẵn sàng cho nhiều hơn.
          </h2>
          <p>
            Hàng đợi SQS điều phối công việc. EC2 mở rộng theo nhu cầu. Model
            được lưu trên S3 và phục vụ qua Lambda, với cùng phiên bản runtime.
          </p>
          <Button onClick={start}>Khám phá workspace</Button>
        </div>
        <div className="platform-details">
          {[
            {
              icon: ShieldCheck,
              title: "Dữ liệu có chủ sở hữu",
              text: "Cognito xác thực người dùng. Dataset và thí nghiệm được phân quyền theo workspace.",
            },
            {
              icon: Activity,
              title: "Biết điều gì đang diễn ra",
              text: "Trạng thái job, kết quả validation và logs CloudWatch giúp bạn theo dõi mỗi lần train.",
            },
            {
              icon: Code2,
              title: "Kết nối bằng một API",
              text: "Thử JSON ngay trên giao diện, sao chép cURL và quản lý key cho từng endpoint.",
            },
          ].map((item) => (
            <div key={item.title}>
              <item.icon size={23} />
              <div>
                <h3>{item.title}</h3>
                <p>{item.text}</p>
              </div>
            </div>
          ))}
        </div>
      </section>
      <footer className="landing-footer">
        <Logo light />
        <span>Cloud AutoML Studio</span>
        <span>Designed for your next experiment.</span>
      </footer>
    </div>
  );
}

function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}
function Overview({ go }: { go: (p: string) => void }) {
  const jobs = useList<Job>("/jobs"),
    datasets = useList<Dataset>("/datasets"),
    deployments = useList<Deployment>("/deployments");
  return (
    <>
      <PageHeading
        eyebrow="YOUR MACHINE LEARNING STUDIO"
        title="Không gian cho ý tưởng mới."
        description="Dữ liệu, thí nghiệm và mô hình. Tất cả ở một nơi."
        action={
          <Button onClick={() => go("/app/new")}>
            <Plus size={18} />
            Thí nghiệm mới
          </Button>
        }
      />
      <div className="welcome-banner">
        <div>
          <span className="small-tag">FROM DATA TO DECISIONS</span>
          <h2>
            Thí nghiệm tiếp theo
            <br />
            bắt đầu từ dữ liệu của bạn.
          </h2>
          <p>Upload CSV. Chọn mục tiêu. Khám phá khả năng.</p>
          <Button kind="dark" onClick={() => go("/app/new")}>
            Bắt đầu với một dataset
          </Button>
        </div>
        <div className="banner-art" aria-hidden="true">
          <span className="art-ring" />
          <span className="art-ring second" />
          <div className="art-block block-one">
            <Database size={30} />
          </div>
          <div className="art-block block-two">
            <Layers3 size={38} />
          </div>
          <div className="art-block block-three">
            <Zap size={25} />
          </div>
        </div>
      </div>
      <ErrorBox message={jobs.error || datasets.error || deployments.error} />
      <div className="stat-grid">
        {[
          {
            label: "Datasets đã tải",
            value: datasets.items.length,
            icon: Database,
            note: "Nguồn dữ liệu của bạn",
          },
          {
            label: "Thí nghiệm",
            value: jobs.items.length,
            icon: FlaskConical,
            note: `${jobs.items.filter((j) => j.status === "TRAINING" || j.status === "QUEUED").length} đang xử lý`,
          },
          {
            label: "Endpoint hoạt động",
            value: deployments.items.filter((d) => d.status === "ACTIVE")
              .length,
            icon: Box,
            note: "Sẵn sàng nhận dự đoán",
          },
        ].map((s) => (
          <div className="stat-card" key={s.label}>
            <div>
              <span>{s.label}</span>
              <s.icon size={19} />
            </div>
            <strong>
              {jobs.loading || datasets.loading || deployments.loading
                ? "—"
                : fmt(s.value)}
            </strong>
            <small>{s.note}</small>
          </div>
        ))}
      </div>
      {(jobs.cursor || datasets.cursor || deployments.cursor) && (
        <p className="fine-print">
          Thống kê dựa trên 30 bản ghi gần nhất của mỗi loại.
        </p>
      )}
      <div className="overview-bottom">
        <section className="panel">
          <div className="panel-heading">
            <h2>Thí nghiệm gần đây</h2>
            <button className="text-button" onClick={() => go("/app/jobs")}>
              Xem tất cả
              <ChevronRight size={16} />
            </button>
          </div>
          {jobs.loading ? (
            <Loading />
          ) : jobs.items.length ? (
            <JobTable items={jobs.items.slice(0, 5)} go={go} />
          ) : (
            <Empty
              icon={<FlaskConical size={26} />}
              headline="Một khởi đầu mới"
              detail="Tạo thí nghiệm đầu tiên để theo dõi quá trình huấn luyện tại đây."
              action={
                <Button kind="secondary" onClick={() => go("/app/new")}>
                  <Plus size={16} />
                  Tạo thí nghiệm
                </Button>
              }
            />
          )}
        </section>
        <section className="quick-guide">
          <span className="eyebrow">QUICK START</span>
          <h2>Từ CSV đến API</h2>
          <div className="guide-item">
            <span>
              <UploadCloud size={17} />
            </span>
            <div>
              <strong>Tải dữ liệu của bạn</strong>
              <p>CSV tối đa 10 MB</p>
            </div>
          </div>
          <div className="guide-item">
            <span>
              <WandSparkles size={17} />
            </span>
            <div>
              <strong>Chuẩn bị & train</strong>
              <p>Classification hoặc regression</p>
            </div>
          </div>
          <div className="guide-item">
            <span>
              <Rocket size={17} />
            </span>
            <div>
              <strong>Triển khai & dự đoán</strong>
              <p>Endpoint với API key riêng</p>
            </div>
          </div>
          <div className="guide-note">
            <Sparkles size={17} />
            <p>
              Chưa có dữ liệu? Dùng dataset mẫu customer churn khi tạo thí
              nghiệm.
            </p>
          </div>
        </section>
      </div>
    </>
  );
}
function JobTable({ items, go }: { items: Job[]; go: (p: string) => void }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>THÍ NGHIỆM</th>
            <th>TRẠNG THÁI</th>
            <th>BÀI TOÁN</th>
            <th>THỜI GIAN</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {items.map((job) => (
            <tr key={job.id}>
              <td>
                <button
                  className="table-link"
                  onClick={() => go("/app/jobs/" + job.id)}
                >
                  <span className="table-icon">
                    <FlaskConical size={17} />
                  </span>
                  <span>
                    <strong>{job.name}</strong>
                    <small>{job.id.slice(0, 8)}</small>
                  </span>
                </button>
              </td>
              <td>
                <Badge status={job.status} />
              </td>
              <td>{job.task}</td>
              <td className="muted nowrap">{date(job.created_at)}</td>
              <td>
                <button
                  className="icon-button"
                  aria-label={`Xem ${job.name}`}
                  onClick={() => go("/app/jobs/" + job.id)}
                >
                  <ChevronRight size={18} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function Jobs({ go }: { go: (p: string) => void }) {
  const list = useList<Job>("/jobs"),
    [filter, setFilter] = useState(""),
    [status, setStatus] = useState("ALL");
  return (
    <>
      <PageHeading
        eyebrow="EXPERIMENTS"
        title="Mỗi lần thử, một khám phá."
        description="Theo dõi hàng đợi, quá trình huấn luyện và kết quả model."
        action={
          <Button onClick={() => go("/app/new")}>
            <Plus size={18} />
            Thí nghiệm mới
          </Button>
        }
      />
      <ErrorBox message={list.error} />
      <div className="panel">
        <div className="list-toolbar">
          <div className="search-field">
            <Search size={17} />
            <input
              aria-label="Tìm thí nghiệm"
              placeholder="Tìm tên thí nghiệm…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
          <div className="toolbar-actions">
            <select
              aria-label="Lọc trạng thái"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="ALL">Tất cả trạng thái</option>
              {["QUEUED", "TRAINING", "COMPLETED", "FAILED", "CANCELLED"].map(
                (s) => (
                  <option key={s} value={s}>
                    {statusLabel[s]}
                  </option>
                ),
              )}
            </select>
            <Button kind="secondary small" onClick={() => void list.refresh()}>
              <RefreshCw size={15} />
              Làm mới
            </Button>
          </div>
        </div>
        {list.loading ? (
          <Loading />
        ) : list.items.length ? (
          <JobTable
            items={list.items.filter(
              (j) =>
                j.name.toLowerCase().includes(filter.toLowerCase()) &&
                (status === "ALL" || status === j.status),
            )}
            go={go}
          />
        ) : (
          <Empty
            icon={<FlaskConical size={28} />}
            headline="Chưa có thí nghiệm"
            detail="Bắt đầu với dữ liệu của bạn hoặc dataset mẫu."
            action={
              <Button onClick={() => go("/app/new")}>Tạo thí nghiệm</Button>
            }
          />
        )}
        <Pagination cursor={list.cursor} more={list.more} />
      </div>
    </>
  );
}
function Pagination({
  cursor,
  more,
}: {
  cursor: string | null;
  more: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  return cursor ? (
    <div className="pagination">
      <Button
        kind="secondary"
        disabled={busy}
        onClick={() => {
          setBusy(true);
          void more().finally(() => setBusy(false));
        }}
      >
        Tải thêm
      </Button>
    </div>
  ) : null;
}
function PreviewTable({ profile }: { profile: Profile }) {
  return (
    <div className="table-scroll preview-table">
      <table>
        <thead>
          <tr>
            {profile.columns.map((c) => (
              <th key={c.name}>{c.name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {profile.preview.slice(0, 5).map((r, i) => (
            <tr key={i}>
              {profile.columns.map((c) => (
                <td key={c.name}>
                  {r[c.name] || <span className="null-value">null</span>}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function Datasets({ go }: { go: (p: string) => void }) {
  const list = useList<Dataset>("/datasets"),
    [selected, setSelected] = useState<Dataset | null>(null),
    [error, setError] = useState("");
  const inspect = async (d: Dataset) => {
    try {
      setSelected(await api<Dataset>("/datasets/" + d.dataset_id));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <>
      <PageHeading
        eyebrow="DATA LIBRARY"
        title="Mọi mô hình bắt đầu ở đây."
        description="Quản lý dữ liệu nguồn và các phiên bản đã tiền xử lý."
        action={
          <Button onClick={() => go("/app/new")}>
            <UploadCloud size={18} />
            Upload dataset
          </Button>
        }
      />
      <ErrorBox message={error || list.error} />
      {list.loading ? (
        <Loading />
      ) : !list.items.length ? (
        <div className="panel">
          <Empty
            icon={<Database size={28} />}
            headline="Thư viện đang trống"
            detail="Upload file CSV để khám phá dữ liệu và bắt đầu thí nghiệm."
            action={
              <Button onClick={() => go("/app/new")}>
                Thêm dataset đầu tiên
              </Button>
            }
          />
        </div>
      ) : (
        <div className="dataset-grid">
          {list.items.map((d) => (
            <button
              className="dataset-card"
              key={d.id}
              onClick={() => void inspect(d)}
            >
              <div>
                <span className="dataset-file-icon">
                  <FileSpreadsheet size={25} />
                </span>
                <span className={`small-tag ${d.prepared ? "green" : ""}`}>
                  {d.prepared ? "ĐÃ XỬ LÝ" : "DỮ LIỆU GỐC"}
                </span>
              </div>
              <h3>{d.name}</h3>
              <p>
                {d.profile
                  ? `${fmt(d.profile.rows)} dòng · ${d.profile.columns.length} cột`
                  : "Chưa hoàn tất upload"}
              </p>
              <div className="dataset-card-footer">
                <span>{date(d.created_at)}</span>
                <span>{bytes(d.profile?.size_bytes)}</span>
              </div>
            </button>
          ))}
        </div>
      )}
      <Pagination cursor={list.cursor} more={list.more} />
      {selected && (
        <Modal title={selected.name} close={() => setSelected(null)}>
          <div className="modal-body">
            {selected.profile ? (
              <>
                <ProfileSummary profile={selected.profile} />
                <PreviewTable profile={selected.profile} />
                <div className="modal-actions">
                  <Button
                    onClick={() =>
                      go("/app/new?dataset=" + selected.dataset_id)
                    }
                  >
                    Dùng dữ liệu này
                  </Button>
                </div>
              </>
            ) : (
              <p>Upload chưa hoàn tất. Hãy tạo một upload mới.</p>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}
function ProfileSummary({ profile }: { profile: Profile }) {
  return (
    <div className="profile-stats">
      {[
        { label: "Dòng dữ liệu", value: fmt(profile.rows) },
        { label: "Cột", value: profile.columns.length },
        { label: "Giá trị thiếu", value: fmt(profile.missing_cells) },
        { label: "Dòng trùng", value: fmt(profile.duplicates) },
      ].map((s) => (
        <div key={s.label}>
          <strong>{s.value}</strong>
          <span>{s.label}</span>
        </div>
      ))}
    </div>
  );
}

function NewExperiment({ go }: { go: (p: string) => void }) {
  const [step, setStep] = useState(0),
    [dataset, setDataset] = useState<Dataset | null>(null),
    [preparedDataset, setPreparedDataset] = useState<Dataset | null>(null),
    [target, setTarget] = useState(""),
    [drops, setDrops] = useState<string[]>([]),
    [trim, setTrim] = useState(true),
    [dedupe, setDedupe] = useState(true),
    [missing, setMissing] = useState(true),
    [task, setTask] = useState("classification"),
    [name, setName] = useState(""),
    [seconds, setSeconds] = useState(60),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [step]);
  useEffect(() => {
    const id = new URLSearchParams(location.search).get("dataset");
    if (id) {
      setBusy(true);
      api<Dataset>("/datasets/" + id)
        .then((d) => {
          setDataset(d);
          setTarget(d.target || d.profile?.columns.at(-1)?.name || "");
          setName((d.name.replace(/\.csv$/, "") + " experiment").slice(0, 120));
          setStep(1);
        })
        .catch((e) => setError(e.message))
        .finally(() => setBusy(false));
    }
  }, []);
  async function select(file?: File) {
    if (!file || busy) return;
    setError("");
    setBusy(true);
    try {
      const d = await upload(file);
      setDataset(d);
      setPreparedDataset(null);
      setDrops([]);
      setTarget(d.profile!.columns.at(-1)!.name);
      setName((file.name.replace(/\.csv$/, "") + " experiment").slice(0, 120));
      setStep(1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function preprocess() {
    setBusy(true);
    setError("");
    try {
      const d = await api<Dataset>(
        `/datasets/${dataset!.dataset_id}/preprocess`,
        {
          target,
          drop_columns: drops,
          trim_strings: trim,
          drop_duplicates: dedupe,
          drop_missing_target: missing,
        },
      );
      setPreparedDataset(d);
      setStep(2);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function train() {
    setBusy(true);
    setError("");
    try {
      const j = await api<{ job_id: string }>("/jobs", {
        dataset_id: preparedDataset!.dataset_id,
        name,
        target,
        task,
        time_limit: seconds,
      });
      go("/app/jobs/" + j.job_id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const profile = step === 2 ? preparedDataset?.profile : dataset?.profile;
  return (
    <>
      <PageHeading
        eyebrow="NEW EXPERIMENT"
        title="Biến dữ liệu thành khả năng."
        description="Ba bước để bắt đầu huấn luyện mô hình đầu tiên."
      />
      <div className="wizard-steps">
        {["Upload dữ liệu", "Tiền xử lý", "Cấu hình & train"].map(
          (label, i) => (
            <div
              key={label}
              className={i === step ? "current" : i < step ? "done" : ""}
            >
              <span>{i < step ? <Check size={16} /> : i + 1}</span>
              <strong>{label}</strong>
              {i < 2 && <i />}
            </div>
          ),
        )}
      </div>
      <ErrorBox message={error} />
      <div className="wizard-layout">
        <div className="panel wizard-panel">
          {step === 0 && (
            <>
              <div className="panel-heading">
                <div>
                  <h2>Dữ liệu của bạn, điểm khởi đầu.</h2>
                  <p>Chọn một file CSV với dòng đầu tiên là tên các cột.</p>
                </div>
                <span className="small-tag">CSV</span>
              </div>
              <div
                className={`dropzone ${drag ? "dragging" : ""}`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDrag(true);
                }}
                onDragLeave={() => setDrag(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDrag(false);
                  void select(e.dataTransfer.files[0]);
                }}
              >
                <span className="upload-orb">
                  {busy ? (
                    <Loader2 className="spin" size={30} />
                  ) : (
                    <UploadCloud size={32} />
                  )}
                </span>
                <h3>
                  {busy
                    ? "Đang upload & phân tích dữ liệu…"
                    : "Thả file CSV vào đây"}
                </h3>
                <p>hoặc chọn file từ máy tính của bạn</p>
                <input
                  ref={input}
                  type="file"
                  accept=".csv,text/csv"
                  className="visually-hidden"
                  aria-label="Chọn file CSV"
                  onChange={(e) => void select(e.target.files?.[0])}
                />
                <Button
                  kind="secondary"
                  disabled={busy}
                  onClick={() => input.current?.click()}
                >
                  Chọn file
                </Button>
                <small>UTF-8 · Tối đa 10 MB · 100.000 dòng</small>
              </div>
              <div className="sample-dataset">
                <span className="table-icon">
                  <FileSpreadsheet size={22} />
                </span>
                <div>
                  <strong>Chưa có dataset? Bắt đầu với dữ liệu mẫu.</strong>
                  <p>Customer churn · 240 dòng · 6 cột · dữ liệu tổng hợp</p>
                </div>
                <Button
                  kind="subtle small"
                  disabled={busy}
                  onClick={() => void select(sampleFile())}
                >
                  Dùng mẫu
                </Button>
              </div>
            </>
          )}
          {step === 1 && profile && (
            <>
              <div className="panel-heading">
                <div>
                  <h2>Hiểu dữ liệu trước khi train.</h2>
                  <p>{dataset!.name}</p>
                </div>
                <Badge status="READY" />
              </div>
              <div className="wizard-content">
                <ProfileSummary profile={profile} />
                <label className="field">
                  Cột mục tiêu{" "}
                  <span>Mô hình sẽ dự đoán giá trị của cột này.</span>
                  <select
                    value={target}
                    onChange={(e) => {
                      setTarget(e.target.value);
                      setDrops(drops.filter((c) => c !== e.target.value));
                    }}
                  >
                    {profile.columns.map((c) => (
                      <option key={c.name}>{c.name}</option>
                    ))}
                  </select>
                </label>
                <div className="columns-table">
                  <table>
                    <thead>
                      <tr>
                        <th>DÙNG</th>
                        <th>CỘT</th>
                        <th>KIỂU</th>
                        <th>THIẾU</th>
                        <th>KHÁC NHAU</th>
                      </tr>
                    </thead>
                    <tbody>
                      {profile.columns.map((c) => (
                        <tr key={c.name}>
                          <td>
                            <input
                              aria-label={`Dùng cột ${c.name}`}
                              type="checkbox"
                              checked={!drops.includes(c.name)}
                              disabled={target === c.name}
                              onChange={(e) =>
                                setDrops(
                                  e.target.checked
                                    ? drops.filter((d) => d !== c.name)
                                    : [...drops, c.name],
                                )
                              }
                            />
                          </td>
                          <td>
                            <strong>{c.name}</strong>
                            {target === c.name && (
                              <span className="target-tag">TARGET</span>
                            )}
                          </td>
                          <td className="muted">{c.type}</td>
                          <td className={c.missing ? "warning-text" : ""}>
                            {c.missing}
                          </td>
                          <td>{c.unique}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="form-section">
                  <h3>Làm sạch dữ liệu</h3>
                  <label className="check-option">
                    <input
                      type="checkbox"
                      checked={trim}
                      onChange={(e) => setTrim(e.target.checked)}
                    />
                    <span>Loại khoảng trắng ở đầu và cuối chuỗi</span>
                  </label>
                  <label className="check-option">
                    <input
                      type="checkbox"
                      checked={dedupe}
                      onChange={(e) => setDedupe(e.target.checked)}
                    />
                    <span>Loại dòng trùng lặp</span>
                  </label>
                  <label className="check-option">
                    <input
                      type="checkbox"
                      checked={missing}
                      onChange={(e) => setMissing(e.target.checked)}
                    />
                    <span>Loại dòng thiếu giá trị mục tiêu</span>
                  </label>
                  <p className="fine-print">
                    Giá trị thiếu ở feature được AutoGluon xử lý trong quá trình
                    train. Bản dữ liệu gốc được giữ nguyên.
                  </p>
                </div>
                <h3 className="preview-heading">Xem trước dữ liệu</h3>
                <PreviewTable profile={profile} />
              </div>
              <div className="wizard-actions">
                <Button
                  kind="subtle"
                  disabled={busy}
                  onClick={() => {
                    setStep(0);
                    setDrops([]);
                  }}
                >
                  Chọn file khác
                </Button>
                <Button
                  disabled={busy || !target}
                  onClick={() => void preprocess()}
                >
                  {busy ? (
                    <Loader2 className="spin" size={17} />
                  ) : (
                    <WandSparkles size={17} />
                  )}
                  Áp dụng & tiếp tục
                </Button>
              </div>
            </>
          )}
          {step === 2 && profile && (
            <>
              <div className="panel-heading">
                <div>
                  <h2>Sẵn sàng cho một khám phá mới.</h2>
                  <p>Cấu hình bài toán và thời gian huấn luyện.</p>
                </div>
                <FlaskConical size={24} />
              </div>
              <div className="wizard-content">
                <div className="success-note">
                  <CheckCircle2 size={20} />
                  <span>
                    Dữ liệu đã sẵn sàng:{" "}
                    <strong>
                      {fmt(profile.rows)} dòng, {profile.columns.length - 1}{" "}
                      features
                    </strong>
                    . Đã loại{" "}
                    {Number(preparedDataset!.report?.input_rows || profile.rows) -
                      profile.rows}{" "}
                    dòng.
                  </span>
                </div>
                <label className="field">
                  Tên thí nghiệm
                  <input
                    value={name}
                    maxLength={120}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Customer churn v1"
                  />
                </label>
                <div className="field">
                  Bài toán
                  <div className="task-options">
                    {[
                      {
                        value: "classification",
                        title: "Classification",
                        desc: "Dự đoán một nhãn",
                        icon: Layers3,
                      },
                      {
                        value: "regression",
                        title: "Regression",
                        desc: "Dự đoán một con số",
                        icon: Activity,
                      },
                      {
                        value: "tabular",
                        title: "Tự động",
                        desc: "AutoGluon suy luận",
                        icon: Sparkles,
                      },
                    ].map((t) => (
                      <button
                        key={t.value}
                        className={task === t.value ? "chosen" : ""}
                        onClick={() => setTask(t.value)}
                      >
                        <t.icon size={22} />
                        <strong>{t.title}</strong>
                        <span>{t.desc}</span>
                      </button>
                    ))}
                  </div>
                </div>
                <label className="field">
                  Thời gian huấn luyện
                  <span>
                    Ngân sách cho AutoGluon fit; thời gian khởi động EC2 được
                    tính riêng.
                  </span>
                  <select
                    value={seconds}
                    onChange={(e) => setSeconds(Number(e.target.value))}
                  >
                    <option value={30}>30 giây — thử nhanh</option>
                    <option value={60}>1 phút — bắt đầu</option>
                    <option value={180}>3 phút — khám phá thêm</option>
                    <option value={300}>5 phút</option>
                    <option value={600}>10 phút</option>
                  </select>
                </label>
                <div className="train-summary">
                  <span>
                    Target <strong>{target}</strong>
                  </span>
                  <span>
                    Model <strong>LightGBM</strong>
                  </span>
                  <span>
                    Runtime <strong>AutoGluon 1.4</strong>
                  </span>
                </div>
              </div>
              <div className="wizard-actions">
                <Button
                  kind="subtle"
                  disabled={busy}
                  onClick={() => setStep(1)}
                >
                  Quay lại dữ liệu
                </Button>
                <Button
                  disabled={busy || !name.trim()}
                  onClick={() => void train()}
                >
                  {busy ? (
                    <Loader2 size={17} className="spin" />
                  ) : (
                    <Play size={17} />
                  )}
                  Bắt đầu huấn luyện
                </Button>
              </div>
            </>
          )}
        </div>
        <aside className="wizard-aside">
          <div className="tip-icon">
            <Sparkles size={21} />
          </div>
          <h3>
            {step === 0
              ? "Dữ liệu tốt. Model tốt hơn."
              : step === 1
                ? "Chọn đúng điều cần dự đoán."
                : "Compute khi bạn cần."}
          </h3>
          <p>
            {step === 0
              ? "Mỗi dòng là một quan sát. Mỗi cột là một thuộc tính. Thêm cột kết quả để mô hình có thể học."
              : step === 1
                ? "Target là câu trả lời bạn muốn model tìm ra. Bỏ các cột ID hoặc dữ liệu tiết lộ trực tiếp kết quả để tránh rò rỉ dữ liệu."
                : "Job được đưa vào hàng đợi. Auto Scaling khởi động EC2 worker để huấn luyện, rồi lưu model an toàn trên S3."}
          </p>
          <div className="aside-divider" />
          <div className="aside-detail">
            <ShieldCheck size={17} />
            <span>Dữ liệu tách biệt theo tài khoản</span>
          </div>
          <div className="aside-detail">
            <Database size={17} />
            <span>Lưu trữ trên Amazon S3</span>
          </div>
          <div className="aside-detail">
            <Server size={17} />
            <span>Worker không mở cổng inbound</span>
          </div>
          {step === 2 && (
            <div className="notice">
              Job đầu tiên có thể chờ vài phút để EC2 khởi động và tải image.
            </div>
          )}
        </aside>
      </div>
    </>
  );
}

function JobDetail({
  id,
  go,
  keepKey,
}: {
  id: string;
  go: (p: string) => void;
  keepKey: (id: string, key: string) => void;
}) {
  const [job, setJob] = useState<Job | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [deployed, setDeployed] = useState<DeployResult | null>(null);
  useEffect(() => {
    let alive = true,
      timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const data = await api<Job>("/jobs/" + id);
        if (alive) {
          setJob(data);
          setError("");
          if (["QUEUED", "TRAINING"].includes(data.status))
            timer = setTimeout(() => void poll(), 4000);
        }
      } catch (e) {
        if (alive) {
          setError((e as Error).message);
          timer = setTimeout(() => void poll(), 10000);
        }
      }
    }
    void poll();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [id]);
  async function action(kind: string) {
    setBusy(true);
    setError("");
    try {
      if (kind === "deploy") {
        const d = await api<DeployResult>("/deploy", { job_id: id });
        keepKey(d.deployment_id, d.api_key);
        setDeployed(d);
      } else if (kind === "retry") {
        const j = await api<{ job_id: string }>(`/jobs/${id}/retry`, {});
        go("/app/jobs/" + j.job_id);
      } else {
        await api(`/jobs/${id}/cancel`, {});
        setJob(await api<Job>("/jobs/" + id));
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!job)
    return (
      <>
        <ErrorBox message={error} />
        <Loading />
      </>
    );
  const stage =
    job.status === "QUEUED"
      ? 0
      : job.status === "TRAINING"
        ? 1
        : job.status === "COMPLETED"
          ? 2
          : -1;
  return (
    <>
      <button className="back-link" onClick={() => go("/app/jobs")}>
        Thí nghiệm / Chi tiết
      </button>
      <PageHeading
        eyebrow="EXPERIMENT DETAILS"
        title={job.name}
        description={`ID ${job.id}`}
        action={<Badge status={job.status} />}
      />
      <ErrorBox message={error || job.error || ""} />
      <div className="job-layout">
        <section className="panel">
          <div className="panel-heading">
            <h2>Quá trình huấn luyện</h2>
            {["QUEUED", "TRAINING"].includes(job.status) && (
              <span className="live-label">
                <RefreshCw size={13} className="spin" />
                Tự cập nhật
              </span>
            )}
          </div>
          <div className="timeline">
            {[
              {
                title: "Đưa vào hàng đợi",
                text: "Dataset đã được lưu. Job đang chờ EC2 worker.",
                icon: Layers3,
              },
              {
                title: "Huấn luyện model",
                text: "AutoGluon học từ dữ liệu và đánh giá trên tập validation.",
                icon: FlaskConical,
              },
              {
                title: "Model sẵn sàng",
                text: "Artifact đã được lưu lên S3 và sẵn sàng triển khai.",
                icon: CheckCircle2,
              },
            ].map((s, i) => (
              <div
                key={s.title}
                className={`timeline-row ${stage === i ? "current" : ""} ${stage > i ? "done" : ""}`}
              >
                <span>
                  {stage > i ? <Check size={20} /> : <s.icon size={20} />}
                </span>
                <div>
                  <h3>{s.title}</h3>
                  <p>{s.text}</p>
                </div>
                {stage === i && i < 2 && <Loader2 size={18} className="spin" />}
              </div>
            ))}
          </div>
          {job.status === "QUEUED" && (
            <div className="panel-note">
              Worker tự khởi động từ 0. Lần train đầu có thể cần vài phút để tải
              image.
            </div>
          )}
          {job.metrics?.leaderboard && (
            <div className="results-section">
              <div className="panel-heading">
                <h2>Kết quả validation</h2>
                <span className="small-tag">{job.metrics.eval_metric}</span>
              </div>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>MODEL</th>
                      <th>VALIDATION SCORE</th>
                      <th>FIT TIME</th>
                    </tr>
                  </thead>
                  <tbody>
                    {job.metrics.leaderboard.map((m) => (
                      <tr key={m.model}>
                        <td>
                          <strong>{m.model}</strong>
                        </td>
                        <td>{m.score_val?.toFixed(4) ?? "—"}</td>
                        <td>{m.fit_time?.toFixed(2)}s</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="fine-print">
                Score của AutoGluon được quy về “cao hơn là tốt hơn”. Loss như
                RMSE có thể hiển thị số âm. Đây là validation score, chưa phải
                đánh giá trên test set độc lập.
              </p>
            </div>
          )}
        </section>
        <aside className="panel job-config">
          <h2>Cấu hình</h2>
          <dl>
            {[
              ["Bài toán", job.task],
              ["Target", job.target],
              ["Ngân sách train", `${job.time_limit}s`],
              ["Tạo lúc", date(job.created_at)],
              ["Bắt đầu", date(job.started_at)],
              ["Hoàn thành", date(job.finished_at)],
              [
                "Artifact",
                job.metrics?.artifact_bytes
                  ? bytes(job.metrics.artifact_bytes)
                  : "—",
              ],
            ].map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
          {job.status === "COMPLETED" && (
            <Button disabled={busy} onClick={() => void action("deploy")}>
              <Rocket size={17} />
              Triển khai endpoint
            </Button>
          )}
          {job.status === "QUEUED" && (
            <Button
              kind="secondary"
              disabled={busy}
              onClick={() => void action("cancel")}
            >
              Hủy job đang chờ
            </Button>
          )}
          {["FAILED", "CANCELLED"].includes(job.status) && (
            <Button disabled={busy} onClick={() => void action("retry")}>
              <RefreshCw size={17} />
              Tạo lần thử mới
            </Button>
          )}
          <p className="fine-print">
            Model được phục vụ bằng Lambda container với cùng runtime ECR đã
            dùng để train.
          </p>
        </aside>
      </div>
      {deployed && (
        <Modal
          title="Endpoint đã sẵn sàng"
          close={() => {
            setDeployed(null);
            go("/app/endpoints");
          }}
        >
          <div className="modal-body">
            <div className="success-note">
              <CheckCircle2 size={20} />
              Lưu API key này trước khi đóng. Key chỉ hiển thị một lần.
            </div>
            <label className="field">
              API key<code className="key-display">{deployed.api_key}</code>
            </label>
            <CopyButton text={deployed.api_key} />
            <label className="field">
              Endpoint
              <code className="key-display">
                {config.apiUrl}
                {deployed.predict_path}
              </code>
            </label>
            <div className="modal-actions">
              <Button
                onClick={() => {
                  setDeployed(null);
                  go("/app/endpoints");
                }}
              >
                Thử dự đoán
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
function Modal({
  title,
  children,
  close,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    const d = ref.current;
    return () => d?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      aria-label={title}
      className="modal"
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
    >
      <div className="modal-header">
        <h2>{title}</h2>
        <button className="icon-button" aria-label="Đóng" onClick={close}>
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}

function Endpoints({
  keys,
  keepKey,
}: {
  keys: Record<string, string>;
  keepKey: (id: string, key: string) => void;
}) {
  const list = useList<Deployment>("/deployments"),
    [selected, setSelected] = useState<Deployment | null>(null),
    [error, setError] = useState("");
  return (
    <>
      <PageHeading
        eyebrow="MODEL ENDPOINTS"
        title="Đưa dự đoán vào thực tế."
        description="Endpoint của bạn. API key của bạn. Sẵn sàng kết nối ứng dụng."
        action={
          <Button kind="secondary" onClick={() => void list.refresh()}>
            <RefreshCw size={17} />
            Làm mới
          </Button>
        }
      />
      <ErrorBox message={error || list.error} />
      {list.loading ? (
        <Loading />
      ) : !list.items.length ? (
        <div className="panel">
          <Empty
            icon={<Box size={28} />}
            headline="Model tiếp theo đang chờ bạn"
            detail="Hoàn tất một thí nghiệm và chọn Triển khai endpoint để bắt đầu dự đoán."
          />
        </div>
      ) : (
        <div className="endpoint-grid">
          {list.items.map((d) => (
            <article className="endpoint-card" key={d.id}>
              <div className="endpoint-card-top">
                <span className="endpoint-icon">
                  <Box size={24} />
                </span>
                <Badge status={d.status} />
              </div>
              <h3>{d.name}</h3>
              <span className="endpoint-path">
                POST /predict/{d.deployment_id.slice(0, 10)}…
              </span>
              <div className="endpoint-info">
                <span>{d.task}</span>
                <span>Target: {d.target}</span>
              </div>
              <div className="endpoint-card-bottom">
                <span>{date(d.created_at)}</span>
                <Button kind="secondary small" onClick={() => setSelected(d)}>
                  <Code2 size={15} />
                  Mở playground
                </Button>
              </div>
            </article>
          ))}
        </div>
      )}
      <Pagination cursor={list.cursor} more={list.more} />
      {selected && (
        <Modal title="Inference playground" close={() => setSelected(null)}>
          <Playground
            deployment={selected}
            initialKey={keys[selected.deployment_id] || ""}
            keepKey={keepKey}
            changed={() => {
              void list.refresh();
            }}
            onError={setError}
          />
        </Modal>
      )}
    </>
  );
}
function Playground({
  deployment,
  initialKey,
  keepKey,
  changed,
  onError,
}: {
  deployment: Deployment;
  initialKey: string;
  keepKey: (id: string, key: string) => void;
  changed: () => void;
  onError: (s: string) => void;
}) {
  const [key, setKey] = useState(initialKey),
    [rows, setRows] = useState('[\n  {"feature": "value"}\n]'),
    [result, setResult] = useState<unknown>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [revoked, setRevoked] = useState(deployment.status !== "ACTIVE"),
    [confirm, setConfirm] = useState(false),
    [tab, setTab] = useState("request"),
    [latency, setLatency] = useState(0);
  useEffect(() => {
    if (deployment.dataset_id)
      void api<Dataset>("/datasets/" + deployment.dataset_id)
        .then((d) => {
          if (d.profile) {
            const row = { ...d.profile.preview[0] };
            delete row[deployment.target];
            setRows(JSON.stringify([row], null, 2));
          }
        })
        .catch((e) => setError(e.message));
  }, [deployment]);
  const endpoint = config.apiUrl.startsWith("http")
    ? config.apiUrl
    : location.origin + config.apiUrl;
  const curl = `curl '${endpoint}/predict/${deployment.deployment_id}' \\\n  -H 'Content-Type: application/json' \\\n  -H 'X-Api-Key: YOUR_DEPLOYMENT_KEY' \\\n  --data '${JSON.stringify({ rows: parseRows(rows) })?.replace(/'/g, "'\\''")}'`;
  async function predict() {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const parsed = JSON.parse(rows);
      if (!Array.isArray(parsed))
        throw new Error("Dữ liệu phải là mảng các object JSON.");
      const start = performance.now();
      const data = await api(
        `/predict/${deployment.deployment_id}`,
        { rows: parsed },
        "POST",
        key,
      );
      setLatency(Math.round(performance.now() - start));
      setResult(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function rotate() {
    setBusy(true);
    setError("");
    try {
      const data = await api<{ api_key: string }>(
        `/deployments/${deployment.deployment_id}/key`,
        {},
      );
      setKey(data.api_key);
      keepKey(deployment.deployment_id, data.api_key);
      changed();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function revoke() {
    setBusy(true);
    try {
      await api(
        `/deployments/${deployment.deployment_id}`,
        undefined,
        "DELETE",
      );
      setRevoked(true);
      setKey("");
      keepKey(deployment.deployment_id, "");
      changed();
      setConfirm(false);
    } catch (e) {
      setError((e as Error).message);
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal-body playground">
      <div className="endpoint-full">
        <span>POST</span>
        <code>
          {endpoint}/predict/{deployment.deployment_id}
        </code>
        <CopyButton
          text={`${endpoint}/predict/${deployment.deployment_id}`}
          label="URL"
        />
      </div>
      <ErrorBox message={error} />
      {revoked && (
        <div className="notice">
          Endpoint đã bị thu hồi. Tạo deployment mới từ thí nghiệm để tiếp tục.
        </div>
      )}
      <div className="playground-tabs">
        <button
          className={tab === "request" ? "active" : ""}
          onClick={() => setTab("request")}
        >
          Thử dự đoán
        </button>
        <button
          className={tab === "code" ? "active" : ""}
          onClick={() => setTab("code")}
        >
          Tích hợp cURL
        </button>
      </div>
      {tab === "request" ? (
        <>
          <label className="field">
            API key
            <div className="input-action">
              <input
                type="password"
                autoComplete="off"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="Dán key của endpoint này"
              />
              <CopyButton text={key} />
            </div>
          </label>
          <div className="key-controls">
            <span>Key chỉ được giữ trong phiên làm việc trên trang.</span>
            <Button
              kind="subtle small"
              disabled={busy || revoked}
              onClick={() => void rotate()}
            >
              <RefreshCw size={13} />
              Tạo key thay thế
            </Button>
          </div>
          <label className="field">
            Input rows{" "}
            <span>Mảng JSON, tối đa 100 dòng. Không cần cột target.</span>
            <textarea
              spellCheck={false}
              value={rows}
              rows={10}
              onChange={(e) => setRows(e.target.value)}
            />
          </label>
          <Button
            disabled={busy || revoked || !key.trim()}
            onClick={() => void predict()}
          >
            {busy ? <Loader2 size={17} className="spin" /> : <Play size={17} />}
            Chạy dự đoán
          </Button>
          {result !== null && (
            <div className="prediction-output">
              <div>
                <strong>Response</strong>
                <span>{fmt(latency)} ms · bao gồm network/cold start</span>
              </div>
              <pre>{JSON.stringify(result, null, 2)}</pre>
            </div>
          )}
        </>
      ) : (
        <div className="code-block">
          <div>
            <span>Terminal</span>
            <CopyButton text={curl} />
          </div>
          <pre>{curl}</pre>
        </div>
      )}
      <div className="endpoint-danger">
        {confirm ? (
          <>
            <span>Key sẽ ngừng hoạt động ngay. Thu hồi endpoint này?</span>
            <Button
              kind="danger small"
              disabled={busy}
              onClick={() => void revoke()}
            >
              Thu hồi
            </Button>
            <Button kind="subtle small" onClick={() => setConfirm(false)}>
              Giữ lại
            </Button>
          </>
        ) : (
          <button
            className="text-button danger-text"
            disabled={revoked}
            onClick={() => setConfirm(true)}
          >
            Thu hồi endpoint
          </button>
        )}
      </div>
    </div>
  );
}
function parseRows(rows: string) {
  try {
    return JSON.parse(rows);
  } catch {
    return [{ feature: "value" }];
  }
}
function Settings() {
  const [health, setHealth] = useState(""),
    [busy, setBusy] = useState(false);
  const check = async () => {
    setBusy(true);
    try {
      await api("/health");
      setHealth("Kết nối API thành công.");
    } catch (e) {
      setHealth((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <PageHeading
        eyebrow="PLATFORM"
        title="Hạ tầng phía sau mỗi dự đoán."
        description="Cấu hình kết nối và kiến trúc vận hành của workspace."
      />
      <div className="settings-grid">
        <section className="panel settings-panel">
          <h2>Kết nối hiện tại</h2>
          <dl>
            <div>
              <dt>Môi trường</dt>
              <dd>
                {config.local ? "LocalStack + Docker" : "Amazon Web Services"}
              </dd>
            </div>
            <div>
              <dt>Region</dt>
              <dd>{config.region}</dd>
            </div>
            <div>
              <dt>API URL</dt>
              <dd>
                <code>{config.apiUrl}</code>
              </dd>
            </div>
            <div>
              <dt>Xác thực</dt>
              <dd>
                {config.local
                  ? "Local — không yêu cầu đăng nhập"
                  : "Cognito · OAuth 2.0 + PKCE"}
              </dd>
            </div>
          </dl>
          <Button kind="secondary" disabled={busy} onClick={() => void check()}>
            <Activity size={17} />
            Kiểm tra kết nối
          </Button>
          {health && (
            <p className="notice" role="status">
              {health}
            </p>
          )}
          <p className="fine-print">
            Cấu hình được tạo khi deploy và nạp từ /config.js. Không chứa AWS
            secret hoặc API key.
          </p>
        </section>
        <section className="panel settings-panel">
          <h2>Giới hạn workspace</h2>
          <dl>
            <div>
              <dt>Dataset</dt>
              <dd>10 MB · 100.000 dòng · 200 cột</dd>
            </div>
            <div>
              <dt>Train</dt>
              <dd>10–600 giây / lần fit</dd>
            </div>
            <div>
              <dt>Inference</dt>
              <dd>100 dòng / request</dd>
            </div>
            <div>
              <dt>Runtime</dt>
              <dd>AutoGluon 1.4 + LightGBM</dd>
            </div>
            <div>
              <dt>Artifacts</dt>
              <dd>S3 · giới hạn 1 GB / model</dd>
            </div>
          </dl>
          <p className="notice">
            Inference chạy trong Lambda. Cold start hoặc model lớn có thể vượt
            timeout API 28 giây; thử lại để dùng model đã được cache.
          </p>
        </section>
      </div>
      <section className="panel architecture-panel">
        <div className="panel-heading">
          <h2>Kiến trúc AWS</h2>
          <span className="small-tag">END-TO-END</span>
        </div>
        <div className="architecture-flow">
          {[
            { icon: UploadCloud, title: "Frontend", desc: "S3 + CloudFront" },
            {
              icon: ShieldCheck,
              title: "API Gateway",
              desc: "Cognito + Lambda",
            },
            { icon: Layers3, title: "SQS", desc: "Hàng đợi jobs" },
            { icon: Server, title: "EC2 workers", desc: "Auto Scaling 0 → N" },
            { icon: Database, title: "Model storage", desc: "S3 + DynamoDB" },
            { icon: Zap, title: "Inference", desc: "Lambda + ECR" },
          ].map((n) => (
            <div key={n.title}>
              <n.icon size={25} />
              <strong>{n.title}</strong>
              <span>{n.desc}</span>
            </div>
          ))}
        </div>
        <div className="panel-note">
          CloudWatch theo dõi logs và queue. Worker đang train được bảo vệ khỏi
          scale-in; nhóm về 0 khi hàng đợi và job đang xử lý đều trống trong 15
          phút.
        </div>
      </section>
    </>
  );
}
