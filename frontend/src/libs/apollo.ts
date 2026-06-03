import { ApolloClient, ApolloLink, InMemoryCache } from "@apollo/client";
import UploadHttpLink from "apollo-upload-client/UploadHttpLink.mjs";
import { API_BASE_URL } from "./api";

const authLink = new ApolloLink((operation, forward) => {
  const token = localStorage.getItem("session_token");
  operation.setContext(({ headers = {} }: { headers: Record<string, string> }) => ({
    headers: {
      ...headers,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  }));
  return forward(operation);
});

export const client = new ApolloClient({
  link: authLink.concat(
    new UploadHttpLink({ uri: `${API_BASE_URL}/graphql` })
  ),
  cache: new InMemoryCache(),
});
