node {
    
    stage ('Uploading file') {
    env.NODEJS_HOME = "${tool 'Node LTS'}"
    // on linux / mac
    env.PATH="${env.NODEJS_HOME}/bin:${env.PATH}"
    
    sh 'echo "Uploading files to drive"'

     git url: 'https://github.com/rgonzalezp/Markit', 
    credentialsId: '**'

    }

    stage ('Code analysis') {

    sh 'echo “If we had integration tests, they would be here”'

    }
   
    
    
}

