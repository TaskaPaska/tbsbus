# k8s — k3s მრავალ-კვანძიანი orchestration (ფაზა 4)

მთელი pipeline-ის გაშვება k3s კლასტერზე — **4 კვანძი** (proposal-ის „desired"):

| კვანძი | როლი | რა ეშვება |
|--------|------|-----------|
| **atlas** (8GB, always-on) | k3s server (control plane) + storage | postgres, kafka |
| **forge** (32GB) | k3s agent + compute | collector, ingest, api, spark-master, spark-worker |
| **laptop-1/2** (8GB, Linux VM) | k3s agent | spark-worker (მხოლოდ) |

განაწილება nodeSelector-ებით: stateful (postgres/kafka) → atlas; აპლიკაცია/Spark master → forge;
Spark worker-ები → DaemonSet ყველა `ttc/spark=true` კვანძზე (forge + 2 laptop = 3 worker).

> **Spark workers on laptops** = feature-job ნამდვილად ნაწილდება 3 worker-ზე — ეს არის
> „distributed Big Data" დემონსტრაცია. დემოს გარდა laptop-ები ჩართული არ უნდა იყოს.

---

## 1. k3s server (atlas)
```bash
curl -sfL https://get.k3s.io | sh -          # atlas-ზე
sudo cat /var/lib/rancher/k3s/server/node-token   # ← TOKEN agent-ებისთვის
ip -4 addr                                    # ← atlas-ის IP (ATLAS_IP)
```

## 2. agent-ების შეერთება (forge, laptop-1, laptop-2 — თითო Linux-ზე)
```bash
curl -sfL https://get.k3s.io | K3S_URL=https://<ATLAS_IP>:6443 K3S_TOKEN=<TOKEN> sh -
```
> laptop-ები Linux-ს მოითხოვს (k3s agent Linux-ზე) — CLAUDE.md-ის გეგმით მცირე Linux VM თითოზე.

შემოწმება (atlas-დან): `sudo k3s kubectl get nodes` — უნდა ჩანდეს 4 Ready კვანძი.
ქვემოთ `kubectl` = `sudo k3s kubectl` (ან დააკოპირე `/etc/rancher/k3s/k3s.yaml` → `~/.kube/config`).

## 3. კვანძების ლეიბლირება
```bash
kubectl label node <atlas>    ttc/storage=true
kubectl label node <forge>    ttc/role=compute ttc/spark=true
kubectl label node <laptop-1> ttc/spark=true
kubectl label node <laptop-2> ttc/spark=true
```

## 4. images-ის აგება და კვანძებზე გავრცელება
k3s containerd-ს იყენებს (არა docker-ს), ამიტომ ლოკალური images უნდა მოხვდეს თითო კვანძის
containerd-ში. **რეკომენდებული — პატარა registry** (forge-ზე, სადაც Docker და repo არის):

```bash
# forge-ზე (repo root):
docker compose build collector api ingest                    # ttc-* images
docker compose --profile spark build spark-master            # ttc-spark
docker run -d -p 5000:5000 --name registry --restart=always registry:2
for img in ttc-collector ttc-ingest ttc-api ttc-spark; do
  # compose images სხვა სახელით აიგება — გადაიტეგე და push:
  docker tag $(docker compose images -q ${img#ttc-} 2>/dev/null || echo $img) <FORGE_IP>:5000/$img:latest
  docker push <FORGE_IP>:5000/$img:latest
done
```
შემდეგ თითო კვანძზე `/etc/rancher/k3s/registries.yaml`-ში დაამატე insecure registry `<FORGE_IP>:5000`
და manifests-ში image → `<FORGE_IP>:5000/ttc-*:latest` (sed-ით ან kustomize-ით), restart k3s.

**ალტერნატივა (registry-ს გარეშე, თითო კვანძზე):**
```bash
docker save ttc-spark:latest | ssh <node> 'sudo k3s ctr images import -'
```
(ttc-collector/ingest/api → მხოლოდ forge-ზე; ttc-spark → forge + 2 laptop.)

## 5. secret (API_KEY) — არ commit-დება
```bash
kubectl create namespace ttc 2>/dev/null
kubectl -n ttc create secret generic ttc-secret \
  --from-literal=API_KEY=<რეალური-X-Api-Key> \
  --from-literal=POSTGRES_PASSWORD=ttc
```

## 6. ⚠️ atlas-ის systemd collector გაჩერება (double-poll-ის თავიდან)
```bash
sudo systemctl stop ttc-collector     # atlas-ზე — თორემ TTC API ორმაგად იპოლება
```

## 7. apply
```bash
kubectl apply -f 00-namespace.yaml -f 10-postgres.yaml -f 20-kafka.yaml \
              -f 30-app.yaml -f 40-spark.yaml
kubectl -n ttc get pods -o wide          # ნახე რომელ კვანძზე ჯდება რა
```
შემოწმება: Spark master UI — `http://<node-ip>:30808` → **3 Alive Worker**.
API — `curl http://<node-ip>:30500/health`.

## 8. განაწილებული feature-job
```bash
kubectl -n ttc create -f 50-spark-features-job.yaml
kubectl -n ttc logs job/spark-features -f     # "training rows: N" + Postgres table training_row
```
Spark UI-ში დაინახავ task-ებს სამივე worker-ზე გაშლილს — ეს არის 4-კვანძიანი distributed run.

## ცნობილი დელიკატური წერტილები (გადასამოწმებელი ცოცხალ კლასტერზე)
- **Spark standalone DNS** k8s-ში: თუ worker ვერ რეგისტრირდება master-თან, იხ. `SPARK_MASTER_HOST`
  / headless svc (40-spark.yaml). master UI (30808) უნდა აჩვენებდეს 3 worker-ს.
- **client-mode driver.host**: 50-...job.yaml აყენებს `spark.driver.host=$(POD_IP)` — საჭიროა,
  რომ executor-ებმა driver მონახონ.
- **PVC**: k3s-ის ნაგულისხმევი local-path provisioner pod-ს კვანძზე აკრავს (RWO). postgres/kafka
  atlas-ზე რჩება (ttc/storage=true) — მონაცემი იქვე.
- მანიფესტები სტატიკურადაა დაწერილი/გადამოწმებული; ცოცხალი 4-კვანძიანი apply შენი hardware-ის ნაბიჯია.
