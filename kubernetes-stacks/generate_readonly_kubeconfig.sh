# 1. Create a readonly service account
kubectl create serviceaccount readonly-agent -n default

# 2. Create ClusterRole (read only)
kubectl create clusterrole readonly-role \
  --verb=get,list,watch \
  --resource=pods,nodes,events,deployments,services,namespaces,replicasets,statefulsets,daemonsets,configmaps

# 3. Bind the role
kubectl create clusterrolebinding readonly-agent-binding \
  --clusterrole=readonly-role \
  --serviceaccount=default:readonly-agent

# 4. Get the token
TOKEN=$(kubectl create token readonly-agent -n default)

# 5. Get cluster info
CLUSTER_SERVER=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')
CLUSTER_CA=$(kubectl config view --minify --raw -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')

# 6. Create readonly kubeconfig
cat > ~/.kube/readonly-config << YAML
apiVersion: v1
kind: Config
clusters:
- cluster:
    certificate-authority-data: ${CLUSTER_CA}
    server: ${CLUSTER_SERVER}
  name: readonly-cluster
contexts:
- context:
    cluster: readonly-cluster
    user: readonly-agent
  name: readonly-context
current-context: readonly-context
users:
- name: readonly-agent
  user:
    token: ${TOKEN}
YAML

echo "✅ Readonly kubeconfig created at ~/.kube/readonly-config"

# 7. Test it
kubectl --kubeconfig ~/.kube/readonly-config get pods -A