# Stratus — Cloud AutoML Studio

Ứng dụng full stack cho **CSV → preprocess → train AutoGluon trên EC2 Auto Scaling → deploy → predict**.
Frontend React + TypeScript, backend Python, hạ tầng AWS khai báo bằng CloudFormation/SAM.

## Chạy ngay trên máy

Cần Docker Desktop/Engine + Compose v2. Trên Apple Silicon, image ML chạy `linux/amd64`.

```bash
docker compose up --build -d
```

Mở **http://localhost:3000**. Chọn **Thí nghiệm mới → Dùng mẫu → Áp dụng & tiếp tục → Bắt đầu huấn luyện**.
Sau khi hoàn thành, chọn **Triển khai endpoint → Thử dự đoán**. Có thể dùng CSV riêng.

- Frontend: http://localhost:3000
- API: http://localhost:8000
- LocalStack: http://localhost:4566 (S3, SQS, DynamoDB)
- Local không yêu cầu đăng nhập; prediction luôn cần key của deployment.
- LocalStack mô phỏng lưu trữ/hàng đợi; model được AutoGluon/LightGBM huấn luyện và dự đoán thật.
- EC2 Auto Scaling, Cognito, CloudFront và CloudWatch chỉ hoạt động khi triển khai lên AWS.
- Môi trường local phục vụ phát triển; `docker compose down` xóa state LocalStack khi container bị tạo lại.

```bash
python3 scripts/smoke.py --task all  # upload/preprocess/train/deploy/predict thật, hai bài toán
# Tùy chọn: kiểm tra chính Lambda image trong filesystem chỉ đọc + giới hạn RAM 2 GB
docker compose --profile lambda up -d inference
python3 scripts/lambda_smoke.py
docker compose --profile lambda stop inference
# Xem tiến trình
docker compose logs -f worker
# Dừng local
docker compose down
```

## Deploy AWS

Hướng dẫn đầy đủ: **[docs/aws-setup.md](docs/aws-setup.md)**, gồm tài khoản/quyền, region,
network, Cognito, build/push ECR, xác minh Auto Scaling, logs, chi phí và dọn tài nguyên.

```bash
aws configure sso
aws sso login --profile your-profile
export AWS_PROFILE=your-profile
export AWS_DEFAULT_REGION=us-east-1
export STACK_NAME=stratus-automl
export MAX_WORKERS=2
# Không bắt buộc: export BUDGET_EMAIL=you@example.com
bash scripts/deploy.sh
```

Script tự tạo VPC hai public subnet nếu không truyền `VPC_ID` và `SUBNET_IDS`, tạo CloudFront/S3 frontend,
build image **amd64**, push ECR theo digest, deploy backend rồi xuất `/config.js` và publish frontend.
AWS CLI v2, Docker Buildx, Node.js 22+, npm và Python 3.10+ cần có trên máy deploy.
Không cần SAM CLI. AWS tài khoản thật có phát sinh phí; script không tự chạy khi bạn mở repository.

## Chức năng

| Phần | Đã triển khai |
| --- | --- |
| Landing + workspace | Giao diện tiếng Việt, responsive, trạng thái loading/error/empty, navigation |
| Đăng nhập AWS | Cognito Hosted UI, OAuth code + PKCE, refresh token, đăng xuất |
| Dataset | Presigned S3 upload, profile cột, preview, thiếu/trùng, thư viện phân trang |
| Tiền xử lý | Chọn target/features, trim chuỗi, chuẩn hóa giá trị thiếu, bỏ trùng/thiếu target, bản mới bất biến |
| Huấn luyện | Classification, regression, tự suy luận; SQS + AutoGluon/LightGBM; leaderboard, validation metric |
| Job lifecycle | Theo dõi trạng thái, hủy khi chờ, retry tạo job mới, lease owner, heartbeat, xử lý DLQ |
| Scaling | EC2 ASG 0–N theo SQS; bảo vệ worker đang train; về 0 sau 15 phút idle |
| Deployment | Mapping model trong DynamoDB, kiểm tra image digest, key riêng chỉ lưu SHA-256 |
| Inference | Lambda container từ ECR, tải S3 model, cache warm instance, kiểm tra feature, tối đa 100 rows |
| Playground | Gửi JSON, xem predictions/latency, mẫu cURL, xoay key và thu hồi endpoint |
| Hạ tầng | IAM roles, private S3 + CloudFront OAC, DynamoDB PITR, encrypted SQS/EBS, CloudWatch, budget tùy chọn |
| Kiểm thử | Unit/integration Moto, smoke ML thật, TypeScript build, CloudFormation lint, GitHub CI |

## Cấu trúc

```text
frontend/            React + TypeScript + Vite, Nginx container
app/
  controller.py      Routes upload/dataset/job/deployment
  datasets.py        CSV profiling & preprocessing
  services.py        Job, train, deploy, predict, cache
  tasks/             Strategy/Factory cho các bài toán tabular
  infrastructure/    S3, SQS, DynamoDB adapters
  predict.py         Inference HTTP handler và xác thực key
  worker.py          SQS polling + instance scale-in protection
  dlq.py             Đồng bộ job hết retry sang FAILED
  local.py           HTTP adapter + bootstrap LocalStack
infra/
  template.yaml      SAM backend + Cognito + EC2 ASG + alarms/budget
  frontend.yaml      Private S3 + CloudFront HTTPS
  registry.yaml      ECR immutable tags
  network.yaml       VPC, hai public subnet, Internet Gateway
scripts/
  deploy.sh          Build/push/deploy toàn bộ AWS
  write_config.py    Tạo public runtime config từ stack outputs
  smoke.py           Kiểm tra ML end-to-end thật
  lambda_smoke.py    Kiểm tra cold/warm inference qua Lambda runtime emulator
```

## API

Chi tiết payload: **[docs/api.md](docs/api.md)**. Các route quản trị yêu cầu Cognito ID token ở AWS;
`POST /predict/{id}` yêu cầu `X-Api-Key` riêng của endpoint, không dùng Cognito token.

| Method | Route | Chức năng |
| --- | --- | --- |
| GET | `/health` | Kiểm tra API |
| POST | `/uploads` | Cấp presigned POST upload CSV |
| POST | `/datasets/{id}/complete` | Profile + chụp bản dữ liệu bất biến |
| GET | `/datasets`, `/datasets/{id}` | Danh sách / chi tiết dataset |
| POST | `/datasets/{id}/preprocess` | Tạo bản dữ liệu đã xử lý |
| POST / GET | `/jobs` | Tạo / liệt kê thí nghiệm |
| GET | `/jobs/{id}` | Trạng thái, metrics, lỗi |
| POST | `/jobs/{id}/cancel`, `/jobs/{id}/retry` | Hủy job chờ / thử lại |
| POST | `/deploy` | Tạo endpoint + key |
| GET | `/deployments`, `/deployments/{id}` | Danh sách / chi tiết endpoint |
| POST | `/deployments/{id}/key` | Thay key, vô hiệu key cũ |
| DELETE | `/deployments/{id}` | Thu hồi endpoint |
| POST | `/predict/{id}` | Dự đoán một batch rows |

## Phát triển

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
cfn-lint infra/*.yaml
docker compose config --quiet
bash -n scripts/deploy.sh

cd frontend
npm ci
npm run dev       # http://localhost:5173, proxy /api -> :8000
npm run build
```

## Phạm vi và giới hạn

- CSV UTF-8, tối đa 10 MB / 100.000 rows / 200 cột, header ≤128 ký tự; upload trực tiếp S3.
  API inline cũ (`POST /jobs` kèm `csv`) vẫn hỗ trợ, giới hạn 1 MB.
- Tiền xử lý không fit mean/median/encoder trên toàn bộ dataset. AutoGluon xử lý feature trong train;
  validation score chưa thay thế đánh giá bằng test set độc lập.
- Model image là **runtime dùng chung** cho worker và Lambda theo sơ đồ. Artifact model nằm ở S3;
  deploy không build một Docker image riêng cho từng model. Chỉ model từ worker của hệ thống mới được load.
- `time_limit` 10–600 giây là ngân sách fit của AutoGluon, không phải hard timeout cho toàn bộ job.
- Lambda inference 28 giây, 2 GB RAM / `/tmp`. Model giới hạn 1 GB uncompressed, nhưng model nhỏ hơn
  vẫn có thể vượt RAM hoặc cold-start timeout. Khi đó cần giảm dataset/model hoặc dùng endpoint EC2/ECS
  cho bài toán lớn; endpoint EC2/ECS chưa nằm trong implementation này.
- Mỗi process cache một model; luân phiên nhiều deployment gây reload. Không có cam kết latency production.
- Khi đổi image digest, runtime từ chối model cũ để tránh lệch dependency. Cần retrain/redeploy model;
  dừng submit và đợi queue rỗng trước khi upgrade stack.
- Dashboard đếm trên trang gần nhất (30 records mỗi loại), hiển thị chú thích khi có trang tiếp theo.
- Local không phải môi trường multi-user an toàn. AWS dùng Cognito + owner checks cho mỗi tài nguyên;
  quyền truy cập prediction là bearer key, cần giữ ở backend của ứng dụng khách.
- API rate limit ở Gateway là best effort; không có billing quota theo user, thanh toán, custom domain,
  GPU, time-series, NLP hoặc image classification. “Image” trong kiến trúc là Docker image.

Tham khảo thiết kế và nguồn AWS: [docs/architecture.md](docs/architecture.md).
