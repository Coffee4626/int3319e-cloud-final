# Setup AWS cho Stratus

## 1. Chuẩn bị tài khoản và máy deploy

Dùng một AWS account sandbox cho môn học, bật MFA cho tài khoản quản trị. Chọn **us-east-1** theo sơ đồ.
Máy cần AWS CLI v2, Docker Desktop/Engine + Buildx, Node.js 22+, npm, Python 3.10+ và Git.
Nếu dùng AWS Academy/Learner Lab, kiểm tra trước: một số lab không cho tạo IAM roles, Cognito,
Budgets hoặc CloudFront. Template hiện tạo roles riêng; account phải cho phép các dịch vụ đó.

Dùng IAM Identity Center/SSO hoặc role deployment do quản trị viên cấp. Không dùng root access key,
không đưa AWS secret vào frontend, Git hay `/config.js`.

```bash
aws configure sso
aws sso login --profile your-profile
export AWS_PROFILE=your-profile
export AWS_DEFAULT_REGION=us-east-1
aws sts get-caller-identity
```

Trong account sandbox, quản trị viên có thể thực hiện deployment. Với role giới hạn, cần cấp quyền tạo,
cập nhật, mô tả và xóa các loại tài nguyên dưới đây, cùng quyền `iam:PassRole` cho roles do stack tạo.
Đây là yêu cầu quyền **deployment**; roles runtime của Lambda và worker được template giới hạn riêng.

| Nhóm | Quyền triển khai cần có |
| --- | --- |
| CloudFormation | Stacks, change sets, transforms SAM, describe events |
| IAM | Roles, inline policies, instance profiles, PassRole, tạo service-linked role Auto Scaling khi lần đầu |
| EC2 / Auto Scaling | VPC, subnet, IGW/routes, SG, launch template, ASG/scaling policies, EC2 run/terminate |
| SSM | Đọc public parameter AMI Amazon Linux 2023 |
| ECR | Repository, repository policy cho Lambda, scan config, GetAuthorizationToken, push image |
| Lambda / API Gateway | Image functions, invoke permission, SQS mapping, REST API/deployment/stage/authorizer |
| S3 / CloudFront | Bucket, policy/CORS/lifecycle/versioning, upload, distribution/OAC/response headers/invalidation |
| DynamoDB / SQS | Table/GSI/PITR, queue/encryption/redrive policy |
| Cognito | User pool, app client, hosted domain, admin-create-user |
| CloudWatch Logs/Alarms | Log groups, retention, metric alarms |
| Budgets (tùy chọn) | Create/update budget nếu đặt BUDGET_EMAIL |

Kiểm tra quota EC2 On-Demand Standard vCPUs đủ cho `MAX_WORKERS × vCPU(instance)`;
`t3.large` dùng 2 vCPU. Quota Lambda, VPC và CloudFront cũng phải còn chỗ. Nếu account mới có quota EC2=0,
cần yêu cầu tăng quota trước.

## 2. Deploy tự động

```bash
export STACK_NAME=stratus-automl       # 3–30 ký tự thường/số/dấu -, bắt đầu bằng chữ
export MAX_WORKERS=2                  # 1–10, mặc định 2
export WORKER_INSTANCE_TYPE=t3.large  # x86_64, mặc định 2 vCPU / 8 GiB
# Tùy chọn, gửi email khi chi phí account đạt 80% ngân sách 10 USD/tháng:
export BUDGET_EMAIL=you@example.com
bash scripts/deploy.sh
```

Script thực hiện:

1. Xác minh CLI, Docker và account hiện tại; nếu stack đã tồn tại thì kiểm tra queue rỗng.
2. Tạo `stratus-automl-network`: VPC, hai public subnet khác AZ, Internet Gateway, route table.
3. Tạo `stratus-automl-web`: bucket frontend private + CloudFront OAC + HTTPS mặc định.
4. Tạo `stratus-automl-registry`: ECR immutable tags và scan-on-push.
5. Build runtime `linux/amd64` từ Lambda Python 3.12, cài AutoGluon 1.4 + LightGBM,
   kiểm tra import/dependencies, push ECR, lấy digest bất biến.
6. Deploy `stratus-automl`: API Gateway, Cognito, controller/predict/DLQ Lambda, S3, DynamoDB,
   SQS/DLQ, EC2 ASG, IAM, logs, scaling alarms, optional budget.
7. Build frontend, tạo `config.js` từ outputs (không chứa secret), upload S3 và invalidate CloudFront.

Lần đầu có thể cần nhiều phút để CloudFront provision và tải dependencies. Khi CloudFront invalidation
đang chạy, hãy chờ hoàn tất trước khi kiểm tra bản mới. Script in URL frontend và stack outputs.

Nếu đã có default VPC/public subnets, truyền cả hai biến để bỏ bước tạo network:

```bash
export VPC_ID=vpc-xxxxxxxx
export SUBNET_IDS=subnet-xxxxxxxx,subnet-yyyyyyyy
bash scripts/deploy.sh
```

Các subnet phải cùng VPC, có route `0.0.0.0/0 → Internet Gateway`, DNS hoạt động.
Worker dùng public IPv4 để tải ECR và gọi AWS; security group **không có inbound rule**, không SSH.
Metadata bắt buộc IMDSv2, hop limit 2 cho Docker. Không tạo NAT Gateway để giảm chi phí cố định.
Nếu cần private subnet thực sự, phải bổ sung NAT hoặc đủ VPC endpoints và sửa network interface;
không chỉ thay ID subnet vào template hiện tại.

## 3. Tạo tài khoản đăng nhập

User pool mặc định chỉ cho admin tạo tài khoản, không mở self-signup công khai.
Lấy `UserPoolId` từ stack outputs; dùng console **Cognito → User pools → pool của stack → Users → Create user**,
đặt email và gửi lời mời. Người dùng đăng nhập trên frontend và đổi mật khẩu tạm trong Cognito Hosted UI.

Có thể tạo lời mời bằng CLI (thay email bằng địa chỉ thật của bạn):

```bash
POOL_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs[?OutputKey==`UserPoolId`].OutputValue | [0]' --output text)
aws cognito-idp admin-create-user --user-pool-id "$POOL_ID" \
  --username you@example.com \
  --user-attributes Name=email,Value=you@example.com Name=email_verified,Value=true \
  --desired-delivery-mediums EMAIL
```

Frontend redirect tới `<CloudFront origin>/auth/callback`. Callback/logout URL và CORS được script
cấu hình theo đúng origin. API Gateway kiểm tra Cognito ID token, bao gồm audience app client;
backend lấy `sub` đã xác minh và kiểm tra owner trước khi đọc/ghi từng tài nguyên.

API quản trị dùng `Authorization: <Cognito ID token>` (ID token, không phải access token).
Frontend tự xử lý PKCE, refresh khi token gần hết hạn; không có client secret.

## 4. Chạy một thí nghiệm trên AWS

1. Mở URL CloudFront, đăng nhập.
2. **Thí nghiệm mới → Dùng mẫu** hoặc upload CSV UTF-8 riêng.
3. Chọn `churn` làm target cho mẫu, kiểm tra feature/duplicate/missing, **Áp dụng & tiếp tục**.
4. Chọn classification, thời gian 60 giây rồi **Bắt đầu huấn luyện**.
5. Job ở `QUEUED` khi EC2 boot/pull image. Sau đó chuyển `TRAINING → COMPLETED`.
6. Xem validation metric, chọn **Triển khai endpoint**, lưu API key.
7. Mở playground, gửi JSON rows. Trong ứng dụng khác, dùng cURL mẫu và `X-Api-Key` riêng.

API key là credential riêng của ứng dụng, được kiểm tra trong Lambda bằng SHA-256 + constant-time compare.
Nó **không phải API Gateway usage-plan key**. Quản trị dùng Cognito; Gateway có rate limit best effort.
Không nhúng key prediction vào frontend công khai của sản phẩm khách.

Model được tải từ `models/` trên S3. ECR chứa cùng **runtime image** cho train/inference, không bake
artifact riêng cho từng model. `/deploy` xuất bản mapping + key; không cần build Docker mỗi lần train.

## 5. Xác minh Auto Scaling

Mở **EC2 → Auto Scaling Groups → `<stack>-workers`**:

- Ban đầu `Desired=0`, `Min=0`, `Max=MAX_WORKERS`.
- Gửi một hoặc nhiều jobs. Alarm `QueueHasWork` theo visible SQS messages sẽ tăng thêm 1 worker,
  cooldown 300 giây, không vượt Max. ASG có thể mất vài phút mới boot và pull xong image.
- Worker xử lý một job mỗi lần; các worker xử lý song song.
- Khi nhận job, worker tự bật instance scale-in protection, tắt khi xử lý xong.
- Mỗi 30 giây worker gia hạn lease DynamoDB và visibility SQS.
- Alarm `QueueIdle` cộng **visible + not-visible**, chỉ scale về 0 khi bằng 0 đủ 15 phút.
  Vì vậy job đang train không bị coi là idle.

```bash
aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names "$STACK_NAME-workers" \
  --query 'AutoScalingGroups[0].{Desired:DesiredCapacity,Min:MinSize,Max:MaxSize,Instances:Instances[*].{Id:InstanceId,State:LifecycleState,Protected:ProtectedFromScaleIn}}'
```

Protection không bảo vệ trước lỗi máy, người có quyền terminate thủ công, hay mọi kiểu thay thế hạ tầng.
Đối với crash/OOM, SQS redelivery và DynamoDB lease cho phép attempt mới tiếp nhận. Artifact mỗi attempt
có key riêng; worker cũ không được ghi đè trạng thái của worker mới.

## 6. Vận hành và xử lý lỗi

- **CloudWatch Logs**: `/aws/lambda/<Controller>`, `/aws/lambda/<Predict>`, `/aws/lambda/<DlqProcessor>`;
  log group worker nằm ở output `WorkerLogGroup`.
- **CloudWatch Alarms**: QueueHasWork, QueueIdle, QueueAgeAlarm, PredictErrorsAlarm. Các alarms này
  không gửi email/SNS mặc định; scale alarms có scaling actions. Cảnh báo chi phí là AWS Budgets riêng.
- **DynamoDB**: bảng pay-per-request, GSI `by-owner`, point-in-time recovery; job có timestamps,
  owner/task/target, metrics hoặc error. Trạng thái gồm QUEUED/TRAINING/COMPLETED/FAILED/CANCELLED.
- **SQS/DLQ**: visibility 3600s, lease 3500s, heartbeat 30s; sau 3 lần delivery lỗi vào DLQ.
  DLQ Lambda đánh dấu FAILED rồi ack. Nó giữ lại delivery nếu lease hiện tại còn sống.
  DLQ không phải kho lưu forensic vĩnh viễn: sau xử lý thành công message bị ack; lỗi còn ở DynamoDB/logs.
- **S3**: raw uploads hết hạn sau một ngày; dataset snapshot và model không tự xóa; bật versioning.
- **EC2**: xem ASG Activity nếu chưa launch; kiểm tra quota, subnet/IGW, ECR/IAM. Nếu model không chạy,
  xem worker logs, memory, disk; t3.large có thể thiếu RAM cho dữ liệu phức tạp.
- **401**: hết hạn ID token hoặc sai prediction key. **404**: ID sai hoặc không thuộc user đang đăng nhập.
  **409**: job chưa completed, endpoint đã revoke, hoặc image mismatch. **400**: dữ liệu/config không hợp lệ.
- **502/504 inference**: xem memory/duration/cold start; thử lại sau cold start, giảm batch/model.
  Không có guarantee rằng mọi model <1 GB chạy vừa 2 GB RAM trong 28 giây.
- **403 S3 upload**: kiểm tra URL còn hạn 15 phút, origin đúng CloudFront, file ≤10 MB,
  content type `text/csv`, giữ nguyên fields của presigned POST.
- **Cognito redirect_mismatch**: kiểm tra origin và callback `/auth/callback`, không tự thêm trailing slash.

Frontend local không nhận Cognito account cloud; cấu hình public `local:true` dành riêng cho LocalStack.
Không đổi `AUTH_REQUIRED=false` trong AWS Lambda.

## 7. Nâng cấp

Dừng nhận jobs mới và đợi queue rỗng trước khi chạy lại `scripts/deploy.sh`.
Script kiểm tra queue (metric approximate), nên vẫn cần thực hiện trong thời gian không submit job.

Mỗi build tạo digest mới. Hệ thống hiện chặn model/deployment thuộc digest khác để bảo toàn tương thích
runtime. **Nâng cấp image yêu cầu train và deploy model mới**; endpoint cũ có thể trả 409 sau upgrade.
Nếu cần giữ nhiều runtime phục vụ đồng thời, triển khai stack/version riêng rồi chuyển client sang URL mới.
Không tự xóa ECR image đang được Lambda/EC2 sử dụng.

## 8. Chi phí và dọn tài nguyên

Tài nguyên có thể phát sinh phí: EC2, EBS 50 GB/worker, public IPv4, Lambda, API Gateway, Cognito,
S3/requests/versioning, DynamoDB/PITR, SQS, ECR, CloudWatch, CloudFront và data transfer.
Scale-to-zero chỉ dừng compute workers; không xóa chi phí lưu trữ và các dịch vụ khác.
Không giả định mọi tài nguyên đều thuộc Free Tier. Kiểm tra pricing theo region/account của bạn.
Budget tùy chọn là **toàn account**, 10 USD/tháng, cảnh báo 80%, không tự dừng tài nguyên.

Dừng nhận job, đợi job kết thúc, rồi xóa stack backend trước network:

```bash
aws cloudformation delete-stack --stack-name "$STACK_NAME"
aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME"
aws cloudformation delete-stack --stack-name "$STACK_NAME-web"
aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME-web"
aws cloudformation delete-stack --stack-name "$STACK_NAME-network"
```

Data bucket, DynamoDB và web bucket dùng `Retain`, nên vẫn còn dữ liệu và có thể còn phí.
Kiểm tra backup rồi tự xóa khi chắc chắn không cần. Bucket versioned cần xóa cả versions/delete markers.
ECR ở stack registry riêng: xóa các images khi không còn sử dụng, rồi xóa `$STACK_NAME-registry`.
Chỉ xóa `$STACK_NAME-network` nếu script đã tạo stack đó; không xóa default VPC dùng chung.

## Tài liệu chính thức

- [Scale theo SQS và instance protection](https://docs.aws.amazon.com/autoscaling/ec2/userguide/as-using-sqs-queue.html)
- [Lambda container images](https://docs.aws.amazon.com/lambda/latest/dg/images-create.html)
- [SAM Cognito authorizer](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-controlling-access-to-apis-cognito-user-pool.html)
- [API Gateway keys không thay thế authentication](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-api-usage-plans.html)
- [AutoGluon 1.4 validation leaderboard](https://auto.gluon.ai/1.4/api/autogluon.tabular.TabularPredictor.leaderboard.html)
