// Declarative Jenkins pipeline mirroring the same stages as the GitHub
// Actions workflows in .github/workflows/ (backend pytest against a real
// MySQL container, frontend lint+build, ml-models pytest, Docker image
// builds) - provided because the original project spec names both GitHub
// Actions and Jenkins as CI/CD tools.
//
// HONEST DISCLOSURE: there is no Jenkins controller/agent in this
// development environment, so this pipeline has not been executed against
// a live Jenkins server - unlike the GitHub Actions workflows, which were
// verified for real by pushing to GitHub and watching them run (see
// docs/PHASE_9.md). This file is syntactically complete and follows the
// same well-established Jenkins Pipeline patterns (Docker Pipeline plugin's
// `docker.image(...).withRun(...)` for ephemeral service containers) that a
// real Jenkins installation with the Docker Pipeline plugin would need -
// it is not a placeholder, but it is unverified against a real server.
//
// Requires: a Jenkins agent with Docker available (Docker Pipeline plugin),
// and Node 22 + Python 3.12 either preinstalled on the agent or provided via
// an agent Docker image per stage (omitted here for readability - see
// comments at each stage for the adjustment a real install would need).

pipeline {
    agent any

    environment {
        MYSQL_ROOT_PASSWORD = 'root_password'
        MYSQL_USER           = 'cloudai'
        MYSQL_PASSWORD       = 'cloudai_password'
        SECRET_KEY           = 'ci-test-secret-key-not-for-production-use'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Backend Test') {
            steps {
                script {
                    docker.image('mysql:8.0').withRun(
                        "-e MYSQL_ROOT_PASSWORD=${env.MYSQL_ROOT_PASSWORD} " +
                        "-e MYSQL_DATABASE=cloud_ai_platform_test " +
                        "-e MYSQL_USER=${env.MYSQL_USER} " +
                        "-e MYSQL_PASSWORD=${env.MYSQL_PASSWORD} " +
                        "-p 3306:3306",
                        'mysqladmin ping -h localhost --silent'
                    ) { mysql ->
                        sh 'sleep 15' // give MySQL time to finish first-run init before pytest connects
                        dir('backend') {
                            withEnv([
                                'MYSQL_HOST=127.0.0.1',
                                'MYSQL_PORT=3306',
                                "MYSQL_USER=${env.MYSQL_USER}",
                                "MYSQL_PASSWORD=${env.MYSQL_PASSWORD}",
                                'MYSQL_DATABASE=cloud_ai_platform_test',
                                "SECRET_KEY=${env.SECRET_KEY}"
                            ]) {
                                // Real agent: pip install -r requirements.txt first,
                                // ideally into a per-build virtualenv.
                                sh 'pip install -r requirements.txt'
                                sh 'pytest -v'
                            }
                        }
                    }
                }
            }
        }

        stage('Frontend Build') {
            steps {
                dir('frontend') {
                    sh 'npm ci'
                    sh 'npm run lint'
                    sh 'npm run build'
                }
            }
        }

        stage('ML Models Test') {
            steps {
                script {
                    docker.image('mysql:8.0').withRun(
                        "-e MYSQL_ROOT_PASSWORD=${env.MYSQL_ROOT_PASSWORD} " +
                        "-e MYSQL_DATABASE=cloud_ai_platform_ml_test " +
                        "-e MYSQL_USER=${env.MYSQL_USER} " +
                        "-e MYSQL_PASSWORD=${env.MYSQL_PASSWORD} " +
                        "-p 3306:3306",
                        'mysqladmin ping -h localhost --silent'
                    ) { mysql ->
                        sh 'sleep 15'
                        dir('ml-models') {
                            withEnv([
                                'MYSQL_HOST=127.0.0.1',
                                'MYSQL_PORT=3306',
                                "MYSQL_USER=${env.MYSQL_USER}",
                                "MYSQL_PASSWORD=${env.MYSQL_PASSWORD}",
                                'MYSQL_DATABASE=cloud_ai_platform_ml_test'
                            ]) {
                                sh 'pip install -r requirements.txt'
                                sh 'pytest -v'
                            }
                        }
                    }
                }
            }
        }

        stage('Docker Build') {
            steps {
                sh 'docker build -t cloud-ai-platform-backend:${BUILD_NUMBER} ./backend'
                sh 'docker build -t cloud-ai-platform-frontend:${BUILD_NUMBER} ./frontend'
                sh 'docker build -t cloud-ai-platform-ml-models:${BUILD_NUMBER} ./ml-models'
                // A real deployment would `docker push` here to a registry
                // Jenkins is configured with credentials for - omitted since
                // no such registry/credential exists in this project.
            }
        }
    }

    post {
        always {
            cleanWs()
        }
    }
}
