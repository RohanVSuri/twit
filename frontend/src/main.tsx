import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/globals.css'
import App from './App.tsx'
import { ApolloProvider } from '@apollo/client/react'
import { client } from './libs/apollo.ts'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ApolloProvider client = {client}>
      <App />
    </ApolloProvider>
  </StrictMode>,
)
