# Kiểm chứng implementation

Đã chạy trong môi trường local của repository ngày 27/11/2026:

| Kiểm tra | Kết quả |
| --- | --- |
| `python -m unittest discover -s tests -v` | 29 tests pass |
| `cfn-lint infra/*.yaml` | Pass cho backend, frontend, network và ECR |
| `bash -n scripts/deploy.sh` | Pass |
| `npm run build` | TypeScript + Vite production build pass |
| Docker build `linux/amd64` | AutoGluon import check + pip check pass |
| Smoke classification | Upload → profile → preprocess → SQS/worker → S3 model → deploy → predictions `low`, `high` |
| Smoke regression | Cùng luồng trên, trả số hữu hạn cho hai input rows |
| Key sai | Prediction trả 401 |
| Lambda RIE | Cold và warm invocation pass trong container read-only, Docker memory limit 2 GiB |
| UI Chrome | Landing, dashboard, tạo upload bằng dữ liệu mẫu, profile và preprocess hoạt động |

Moto tests kiểm tra owner isolation, pagination, API key rotation/revocation, auth required, cancel/retry,
lease ownership, DLQ giữ active lease, archive traversal, metadata bounds và các task validation.

LocalStack giả lập S3/SQS/DynamoDB; model training/inference sử dụng AutoGluon/LightGBM thật.
Lambda Runtime Interface Emulator xác minh runtime handler/image, không mô phỏng đầy đủ điều kiện AWS.
Số memory trong log REPORT của emulator không phải phép đo RAM AWS thực tế.

Chưa deploy trên account AWS thật trong phiên này. Vì vậy chưa xác minh bằng live AWS:
Cognito Hosted UI/authorizer, provisioning IAM, ASG 0→N→0, CloudFront propagation, budget email,
latency/cold start dưới tải, chi phí và quota của account. Làm theo `aws-setup.md` để kiểm tra chúng.

Các lỗi phát hiện và đã sửa trong kiểm thử: chuyển kiểu Decimal khi ghi lại DynamoDB/retry,
reserved attribute `metrics`, dependency `typing_extensions` thiếu trong AutoGluon minimal image,
Nginx giữ IP container cũ sau recreate. Không dùng dữ liệu/model giả để thay thế smoke ML thật.
