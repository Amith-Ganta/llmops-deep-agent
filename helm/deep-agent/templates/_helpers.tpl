{{- define "deep-agent.name" -}}
{{- .Chart.Name -}}
{{- end -}}

{{- define "deep-agent.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "deep-agent.labels" -}}
app.kubernetes.io/name: {{ include "deep-agent.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "deep-agent.selectorLabels" -}}
app.kubernetes.io/name: {{ include "deep-agent.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
