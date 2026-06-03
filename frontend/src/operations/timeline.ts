import { gql } from '@apollo/client';

export const ME = gql`
  query Me {
    me {
      id
      twitterUsername
      latestJobId
    }
  }
`;

export const TWITTER_LOGIN = gql`
  mutation TwitterLogin($username: String!, $cookiesJson: String!) {
    twitterLogin(username: $username, cookiesJson: $cookiesJson) {
      success
      username
      sessionToken
      error
    }
  }
`;

export const TWITTER_LOGOUT = gql`
  mutation TwitterLogout {
    twitterLogout
  }
`;

export const FETCH_TIMELINE = gql`
  mutation FetchTimeline {
    fetchTimeline {
      jobId
      status
      steps {
        id
        name
        status
        elapsed
      }
      progress
      error
    }
  }
`;

export const UPLOAD_TIMELINE = gql`
  mutation UploadTimeline($file: Upload!) {
    uploadTimeline(file: $file) {
      jobId
      status
      steps {
        id
        name
        status
        elapsed
      }
      progress
      error
    }
  }
`;

export const RUN_PIPELINE = gql`
  mutation RunPipeline($jobId: ID!) {
    runPipeline(jobId: $jobId) {
      jobId
      status
    }
  }
`;

export const JOB_STATUS = gql`
  query JobStatus($jobId: ID!) {
    jobStatus(jobId: $jobId) {
      jobId
      status
      steps {
        id
        name
        status
        elapsed
      }
      progress
      error
    }
  }
`;

export const DIGEST = gql`
  query Digest($jobId: ID!) {
    digest(jobId: $jobId) {
      clusters {
        id
        label
        summary
        bullets {
          text
          urls
        }
        tweetCount
        totalImportance
      }
    }
  }
`;
