# API contract

Base URL local `http://localhost:8000`; AWS lấy từ output `ApiUrl` (kết thúc bằng `/prod`).
JSON request/response UTF-8. Lỗi có dạng `{"error":"..."}`.

## Authentication

- AWS routes quản trị: `Authorization: <Cognito ID token>`; authorizer Gateway xác minh chữ ký/expiry/audience.
  Không truyền `owner` từ client: server dùng `sub` trong claims đã xác minh.
- `POST /predict/{id}`: `X-Api-Key: <key trả về từ /deploy>`; key chỉ áp dụng cho một endpoint.
- Local không cần Cognito. Prediction vẫn yêu cầu key.
- `OPTIONS` không yêu cầu đăng nhập. CORS AWS chỉ cho origin frontend đã cấu hình.

## Dataset lifecycle

### POST /uploads

```json
{"name":"customers.csv"}
```

Response 201:

```json
{
  "dataset_id":"<id>",
  "upload":{"url":"<S3 URL>","fields":{"key":"<fixed key>","Content-Type":"text/csv","...":"..."}}
}
```

Gửi `multipart/form-data` trực tiếp tới `upload.url`: append tất cả `fields`, sau đó append `file` ở cuối.
Không thêm Cognito header vào S3 request. URL có hạn 15 phút, file 1–10.000.000 bytes.

### POST /datasets/{id}/complete

Body `{}`. Server đọc UTF-8 CSV, kiểm tra tối đa 100.000 dòng/200 cột, header unique và không rỗng,
ít nhất 2 dòng/2 cột. Chụp snapshot sang prefix `datasets/`, ghi profile và trả 200:

```json
{
  "dataset_id":"<id>", "name":"customers.csv", "status":"READY", "prepared":false,
  "profile": {
    "rows":240,"size_bytes":8000,"duplicates":0,"missing_cells":2,
    "columns":[{"name":"age","type":"numeric","missing":0,"unique":45,"examples":["20","21"]}],
    "preview":[{"age":"20","churn":"yes"}]
  }
}
```

Profile/preview chỉ là mẫu: tối đa 5 dòng, cell/examples bị cắt ở 64 ký tự để giữ metadata dưới giới hạn DynamoDB.
File huấn luyện giữ toàn bộ giá trị gốc. Gọi complete sau khi READY trả snapshot hiện có.

### GET /datasets/{id}

Trả metadata/profile dataset thuộc user; 404 nếu không tồn tại/khác owner.

### POST /datasets/{id}/preprocess

```json
{
  "target":"churn",
  "drop_columns":["customer_id"],
  "trim_strings":true,
  "drop_duplicates":true,
  "drop_missing_target":true
}
```

Trả 201 với **dataset_id mới**, `prepared:true`, `target`, `source_id`, `preprocessing`, `report`, `profile`.
Luôn giữ target và ít nhất một feature. Chuỗi rỗng, `NaN`, `null`, `none`, `n/a` (không phân biệt hoa thường)
được coi là missing. Không điền missing label bằng giá trị suy đoán. Không fit imputer/encoder tại bước này.

## Jobs

### POST /jobs

```json
{"dataset_id":"<prepared dataset>","name":"Customer churn v1","task":"classification","time_limit":60}
```

Target lấy từ dataset đã preprocess. `task`: `classification`, `regression`, `tabular` (auto).
`time_limit` integer 10–600 giây. Classification cần ≥2 lớp; regression target phải là số hữu hạn.
Trả 202: `{"job_id":"<id>","status":"QUEUED","task":"classification"}`.

Tương thích API cũ với inline CSV ≤1 MB:

```json
{"csv":"x,y\n1,2\n2,4\n","target":"y","task":"regression","time_limit":60}
```

Ví dụ trên mô tả format; để model/validation có ý nghĩa nên cung cấp nhiều dòng hơn.

### GET /jobs/{id}

Trả metadata, `status`, `created_at`, `started_at`, `finished_at`, `image_uri`.
`COMPLETED` có `metrics`: leaderboard, eval_metric, best_model, problem_type, features, training_rows,
artifact_bytes. `FAILED` có error. Không trả lease owner/token nội bộ.

AutoGluon leaderboard score có quy ước higher-is-better, nên regression loss có thể âm.
Không gọi validation score là test accuracy.

### POST /jobs/{id}/cancel

Body `{}`. Chỉ QUEUED được chuyển CANCELLED bằng conditional update. Job đang train trả 409.
Worker nhận message của job cancelled sẽ ack mà không train.

### POST /jobs/{id}/retry

Body `{}`. Chỉ FAILED/CANCELLED, tạo job ID mới với dữ liệu và cấu hình cũ, image runtime hiện tại.

## Deployments

### POST /deploy

```json
{"job_id":"<completed job>"}
```

Trả 201:

```json
{"deployment_id":"<id>","predict_path":"/predict/<id>","api_key":"<one-time-secret>","task":"classification","image_uri":"<ECR digest>"}
```

Chỉ chấp nhận job COMPLETED thuộc user, cùng image runtime hiện tại. Mỗi lần gọi tạo endpoint mới.
Key chỉ trả lúc tạo/xoay; server lưu SHA-256, không lưu plaintext.

### GET /deployments/{id}

Metadata endpoint; `status` ACTIVE/REVOKED, job_id, dataset_id, task, target, key_prefix, image_uri.
Không trả key/hash. Danh sách cũng không chứa secret.

### POST /deployments/{id}/key

Body `{}`. Thay key ngay, trả `api_key` mới; key cũ không dùng được. Endpoint revoked trả 409.

### DELETE /deployments/{id}

Thu hồi endpoint, giữ metadata và model S3. Không thể dùng endpoint để predict sau khi revoke.
Có thể tạo deployment mới từ cùng job nếu vẫn tương thích image.

## Prediction

### POST /predict/{deployment_id}

```http
Content-Type: application/json
X-Api-Key: <deployment key>
```

```json
{"rows":[{"age":35,"monthly_spend":59,"tenure_months":12,"support_tickets":4,"plan":"standard"}]}
```

Response 200:

```json
{"predictions":["yes"]}
```

1–100 objects, mỗi object ≤200 features, scalar string/number/boolean/null, số phải hữu hạn.
Cần có tất cả feature model sử dụng; không cần cột target. Thứ tự predictions theo rows.
Thiếu key/sai key: 401; revoked/image mismatch: 409; thiếu feature/invalid input: 400.

## Listing và pagination

`GET /datasets`, `GET /jobs`, `GET /deployments`: trang tối đa 30 bản ghi mới nhất của user.

```json
{"items":["..."],"cursor":"<opaque string or null>"}
```

Trang sau: `GET /jobs?cursor=<URL-encoded cursor>`. Cursor không được dùng chéo user/kind.
GSI eventual consistency: record mới có thể xuất hiện chậm một chút; endpoint GET theo ID dùng consistent read.

## Health và HTTP status

`GET /health` → `{"status":"ok","service":"stratus"}`, có auth trên AWS. Đây là liveness API,
không phải kiểm tra toàn bộ EC2/S3/SQS đang healthy.

| Status | Ý nghĩa |
| --- | --- |
| 200/201/202 | Thành công/tạo mới/đã enqueue |
| 400 | Dữ liệu hoặc cấu hình không hợp lệ |
| 401/403 | Thiếu/sai credential; Gateway có thể trả 401/403 trước Lambda |
| 404 | Route/tài nguyên không tồn tại hoặc thuộc user khác |
| 409 | State conflict, revoke hoặc image mismatch |
| 429 | Gateway throttle |
| 500/502/504 | Lỗi runtime, memory, dependency hoặc timeout; xem CloudWatch |
