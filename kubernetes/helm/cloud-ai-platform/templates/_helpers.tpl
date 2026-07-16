{{/*
Common labels applied to every resource this chart renders.
*/}}
{{- define "cloud-ai-platform.labels" -}}
app.kubernetes.io/part-of: cloud-ai-platform
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}
