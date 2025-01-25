import React, { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Toaster } from "@/components/ui/toaster";
import { useToast } from "@/hooks/use-toast";
import { Progress } from "@/components/ui/progress";
import { Card, CardContent } from "@/components/ui/card";

function MultiModalApp() {
  const { toast } = useToast();
  const modalUrl = import.meta.env.VITE_MODAL_URL;

  // State for microphone selection
  const [audioDevices, setAudioDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null);

  // State for audio recording
  const [isRecording, setIsRecording] = useState(false);
  const [recorder, setRecorder] = useState<MediaRecorder | null>(null);
  const [recordedBlob, setRecordedBlob] = useState<Blob | null>(null);

  // Processing states
  const [isProcessing, setIsProcessing] = useState(false);
  const [currentStep, setCurrentStep] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);

  // Result states
  const [transcript, setTranscript] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const [similarityScore, setSimilarityScore] = useState<number | null>(null);
  const [imageDescription, setImageDescription] = useState<string>("");
  const [descriptionAudio, setDescriptionAudio] = useState<string>("");

  // Handle requesting microphone permissions
  const handleRequestMicPermissions = async () => {
    try {
      await navigator.mediaDevices.getUserMedia({ audio: true });
      const devices = await navigator.mediaDevices.enumerateDevices();
      const microphones = devices.filter((d) => d.kind === "audioinput");
      setAudioDevices(microphones);

      if (microphones.length > 0) {
        setSelectedDeviceId(microphones[0].deviceId);
      } else {
        toast({
          title: "No Microphones",
          description: "No microphone devices were found.",
          variant: "destructive",
        });
      }
    } catch (err: any) {
      toast({
        title: "Permission Error",
        description:
          err.name === "NotAllowedError"
            ? "Microphone permission was denied."
            : `Error: ${err.message}`,
        variant: "destructive",
      });
      console.error("Error requesting mic permission:", err);
    }
  };

  // Handle recording start
  const handleStartRecording = async () => {
    try {
      if (!selectedDeviceId) {
        toast({
          title: "No Microphone",
          description: "Please select a microphone first.",
          variant: "destructive",
        });
        return;
      }

      const constraints = {
        audio: {
          deviceId: { exact: selectedDeviceId },
        },
      };

      const mimeType = "audio/webm; codecs=opus";
      if (!MediaRecorder.isTypeSupported(mimeType)) {
        toast({
          title: "Browser Not Supported",
          description: "Your browser doesn't support WebM with Opus codec.",
          variant: "destructive",
        });
        return;
      }

      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      const newRecorder = new MediaRecorder(stream, { mimeType });

      // Clear previous recording data
      setRecordedBlob(null);

      let chunks: Blob[] = [];
      newRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunks.push(event.data);
        }
      };

      newRecorder.onstop = () => {
        const blob = new Blob(chunks, { type: mimeType });
        setRecordedBlob(blob);
        stream.getTracks().forEach((track) => track.stop());
      };

      newRecorder.start(1000);
      setRecorder(newRecorder);
      setIsRecording(true);

      toast({
        title: "Recording Started",
        description: "Speak your prompt clearly into the microphone.",
      });
    } catch (err: any) {
      console.error("Error starting recording:", err);
      toast({
        title: "Recording Error",
        description: err.message,
        variant: "destructive",
      });
    }
  };

  // Handle recording stop
  const handleStopRecording = () => {
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
      setIsRecording(false);
      toast({
        title: "Recording Complete",
        description: "You can now process your recording.",
      });
    }
  };

  // Process the full flow
  const handleProcessFlow = async () => {
    if (!recordedBlob) {
      toast({
        title: "No Recording",
        description: "Please record some audio first.",
        variant: "destructive",
      });
      return;
    }

    setIsProcessing(true);
    setProgress(0);

    try {
      // Step 1: Transcribe audio
      setCurrentStep("transcribing");
      setProgress(20);

      const formData = new FormData();
      formData.append("file", recordedBlob, "recording.webm");

      const transcriptResponse = await fetch(`${modalUrl}/transcribe`, {
        method: "POST",
        body: formData,
      });

      if (!transcriptResponse.ok) {
        const error = await transcriptResponse.json();
        throw new Error(error.detail || "Failed to transcribe audio");
      }

      const transcriptData = await transcriptResponse.json();
      setTranscript(transcriptData.transcript);
      setProgress(40);

      // Step 2: Generate image
      setCurrentStep("generating");
      const imageResponse = await fetch(`${modalUrl}/generate_image`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: transcriptData.transcript }),
      });

      if (!imageResponse.ok) {
        const error = await imageResponse.json();
        throw new Error(error.detail || "Failed to generate image");
      }

      const imageData = await imageResponse.json();
      setImageUrl(imageData.image_url);
      setProgress(60);

      // Step 3: Analyze image similarity
      setCurrentStep("analyzing");
      const analysisResponse = await fetch(
        `${modalUrl}/analyze_image_similarity`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            prompt: transcriptData.transcript,
            image_url: imageData.image_url,
          }),
        },
      );

      if (!analysisResponse.ok) {
        const error = await analysisResponse.json();
        throw new Error(error.detail || "Failed to analyze image");
      }

      const analysisData = await analysisResponse.json();
      setSimilarityScore(analysisData.similarity_score);
      setImageDescription(analysisData.image_description);
      setProgress(80);

      // Step 4: Generate audio description
      setCurrentStep("speaking");
      if (analysisData.image_description) {
        const ttsResponse = await fetch(`${modalUrl}/text_to_speech`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: analysisData.image_description }),
        });

        if (!ttsResponse.ok) {
          const error = await ttsResponse.json();
          throw new Error(error.detail || "Failed to convert text to speech");
        }

        const ttsData = await ttsResponse.json();
        setDescriptionAudio(ttsData.audio);
      }

      setProgress(100);
      toast({
        title: "Processing Complete",
        description: "All steps have been completed successfully.",
      });
    } catch (error: any) {
      console.error("Processing error:", error);
      toast({
        title: "Processing Error",
        description: error.message || "An error occurred during processing",
        variant: "destructive",
      });
    } finally {
      setIsProcessing(false);
      setCurrentStep(null);
    }
  };

  const getStepDescription = () => {
    switch (currentStep) {
      case "transcribing":
        return "Transcribing your audio...";
      case "generating":
        return "Generating an image from your description...";
      case "analyzing":
        return "Analyzing the generated image...";
      case "speaking":
        return "Creating audio description...";
      default:
        return "";
    }
  };

  return (
    <div className="container mx-auto p-4 max-w-4xl">
      <Card className="mb-8">
        <CardContent className="pt-6">
          <h1 className="text-2xl font-bold mb-6">Multi-Modal AI Demo</h1>

          {/* Microphone Setup Section */}
          <div className="space-y-4 mb-8">
            <h2 className="text-xl font-semibold">Microphone Setup</h2>
            <Button
              variant="outline"
              onClick={handleRequestMicPermissions}
              className="w-full sm:w-auto"
            >
              Request Microphone Permissions
            </Button>
            <div className="mt-2">
              <label
                htmlFor="mic-select"
                className="block text-sm text-gray-600 mb-2"
              >
                Choose Microphone:
              </label>
              <select
                id="mic-select"
                className="w-full rounded-md border border-gray-300 shadow-sm p-2"
                value={selectedDeviceId ?? ""}
                onChange={(e) => setSelectedDeviceId(e.target.value)}
              >
                <option value="">Select a microphone...</option>
                {audioDevices.map((device) => (
                  <option key={device.deviceId} value={device.deviceId}>
                    {device.label ||
                      `Microphone ${device.deviceId.slice(0, 8)}`}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Recording Controls */}
          <div className="space-y-4 mb-8">
            <h2 className="text-xl font-semibold">Record Your Prompt</h2>
            <div className="flex gap-2 flex-wrap">
              {!isRecording ? (
                <Button
                  onClick={handleStartRecording}
                  disabled={!selectedDeviceId || isProcessing}
                  className="w-full sm:w-auto"
                >
                  Start Recording
                </Button>
              ) : (
                <Button
                  variant="destructive"
                  onClick={handleStopRecording}
                  className="w-full sm:w-auto"
                >
                  Stop Recording
                </Button>
              )}

              {recordedBlob && (
                <>
                  <div className="w-full">
                    <audio
                      controls
                      src={URL.createObjectURL(recordedBlob)}
                      className="w-full mt-2"
                    />
                  </div>
                  <Button
                    onClick={handleProcessFlow}
                    disabled={isRecording || isProcessing}
                    className="w-full sm:w-auto"
                  >
                    Process Recording
                  </Button>
                </>
              )}
            </div>
          </div>

          {/* Processing Progress */}
          {isProcessing && (
            <div className="space-y-2 mb-8">
              <div className="flex justify-between text-sm">
                <span>{getStepDescription()}</span>
                <span>{progress}%</span>
              </div>
              <Progress value={progress} className="w-full" />
            </div>
          )}

          {/* Results Display */}
          {transcript && (
            <div className="space-y-4 mb-8">
              <h2 className="text-xl font-semibold">Results</h2>

              <div className="space-y-2">
                <h3 className="font-semibold">Your Prompt:</h3>
                <p className="text-gray-700 bg-gray-50 p-4 rounded-lg">
                  {transcript}
                </p>
              </div>

              {imageUrl && (
                <div className="space-y-2">
                  <h3 className="font-semibold">Generated Image:</h3>
                  <img
                    src={imageUrl}
                    alt="AI Generated"
                    className="w-full max-w-2xl rounded-lg shadow-lg"
                  />
                  {similarityScore !== null &&
                    typeof similarityScore === "number" && (
                      <p className="text-sm text-gray-600">
                        Similarity to prompt: {similarityScore.toFixed(1)}%
                      </p>
                    )}
                </div>
              )}

              {imageDescription && (
                <div className="space-y-2">
                  <h3 className="font-semibold">AI Vision Analysis:</h3>
                  <p className="text-gray-700 bg-gray-50 p-4 rounded-lg">
                    {imageDescription}
                  </p>
                  {descriptionAudio && (
                    <div className="mt-4">
                      <h4 className="font-semibold mb-2">Audio Description:</h4>
                      <audio
                        controls
                        src={`data:audio/mp3;base64,${descriptionAudio}`}
                        className="w-full"
                      />
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Toaster />
    </div>
  );
}

export default MultiModalApp;