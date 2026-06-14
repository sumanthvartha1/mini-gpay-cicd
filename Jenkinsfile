pipeline {
    // WHERE to run this pipeline — any available Jenkins agent
    agent any

    // VARIABLES — used throughout the pipeline
    environment {
        AWS_REGION = 'ap-south-2'
        ECR_REGISTRY = '922120356958.dkr.ecr.ap-south-2.amazonaws.com'
        IMAGE_TAG = "${BUILD_NUMBER}"
    }

    stages {

        // ============================================
        // STAGE 1: CHECKOUT — pull code from GitHub
        // ============================================
        stage('Checkout') {
            steps {
                // Jenkins pulls your latest code from GitHub
                // this is equivalent to: git clone your-repo
                checkout scm
                echo "Code checked out successfully"
            }
        }

        // ============================================
        // STAGE 2: BUILD — docker build all 3 images
        // ============================================
        stage('Build Docker Images') {
            steps {
                echo "Building backend image..."
                sh 'docker build -t gpay-backend ./backend'

                echo "Building frontend image..."
                sh 'docker build -t gpay-frontend ./frontend'

                echo "Building nginx image..."
                sh 'docker build -t gpay-nginx ./nginx'

                echo "All images built successfully"
            }
        }

        // ============================================
        // STAGE 3: LOGIN — authenticate Docker to ECR
        // ============================================
        stage('Login to ECR') {
            steps {
                // aws ecr get-login-password generates a temporary token
                // docker login uses that token to authenticate
                // this is the same command you ran manually during ECR push
                sh '''
                    aws ecr get-login-password --region ${AWS_REGION} | \
                    docker login --username AWS --password-stdin ${ECR_REGISTRY}
                '''
                echo "Logged into ECR successfully"
            }
        }

        // ============================================
        // STAGE 4: PUSH — tag and push all images to ECR
        // ============================================
        stage('Push to ECR') {
            steps {
                // TAG each image with ECR address + build number
                // BUILD_NUMBER is auto-incremented by Jenkins (1, 2, 3...)
                sh '''
                    docker tag gpay-backend ${ECR_REGISTRY}/gpay-backend:${IMAGE_TAG}
                    docker tag gpay-backend ${ECR_REGISTRY}/gpay-backend:latest

                    docker tag gpay-frontend ${ECR_REGISTRY}/gpay-frontend:${IMAGE_TAG}
                    docker tag gpay-frontend ${ECR_REGISTRY}/gpay-frontend:latest

                    docker tag gpay-nginx ${ECR_REGISTRY}/gpay-nginx:${IMAGE_TAG}
                    docker tag gpay-nginx ${ECR_REGISTRY}/gpay-nginx:latest
                '''

                // PUSH all images to ECR
                sh '''
                    docker push ${ECR_REGISTRY}/gpay-backend:${IMAGE_TAG}
                    docker push ${ECR_REGISTRY}/gpay-backend:latest

                    docker push ${ECR_REGISTRY}/gpay-frontend:${IMAGE_TAG}
                    docker push ${ECR_REGISTRY}/gpay-frontend:latest

                    docker push ${ECR_REGISTRY}/gpay-nginx:${IMAGE_TAG}
                    docker push ${ECR_REGISTRY}/gpay-nginx:latest
                '''
                echo "All images pushed to ECR successfully"
            }
        }

        // ============================================
        // STAGE 5: CLEANUP — remove local images to save disk
        // ============================================
        stage('Cleanup') {
            steps {
                sh 'docker image prune -f'
                echo "Cleanup complete"
            }
        }
    }

    // ============================================
    // POST ACTIONS — run after all stages complete
    // ============================================
    post {
        success {
            echo "Pipeline completed successfully! Images pushed to ECR."
        }
        failure {
            echo "Pipeline failed! Check the logs above."
        }
    }
}
