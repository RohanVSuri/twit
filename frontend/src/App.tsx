import { BrowserRouter, Routes, Route } from "react-router";
import { UploadPage } from "./pages/UploadPage";
import { PipelinePage } from "./pages/PipelinePage";
import { DigestPage } from "./pages/DigestPage";
import { LoginPage } from "./pages/LoginPage";
import { AuthGuard } from "./components/AuthGuard";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<AuthGuard><UploadPage /></AuthGuard>} />
        <Route path="/pipeline" element={<AuthGuard><PipelinePage /></AuthGuard>} />
        <Route path="/digest/:jobId" element={<AuthGuard><DigestPage /></AuthGuard>} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
