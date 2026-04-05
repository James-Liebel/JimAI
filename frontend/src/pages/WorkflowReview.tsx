import { ReviewBoard } from '../components/review/ReviewBoard';

export default function WorkflowReview() {
    return (
        <ReviewBoard
            scope="jimai"
            variant="page"
            pageTitle="JimAI & platform review"
            pageDescription="Changes that target the JimAI app itself (self-improvement, SelfCode, models, skills). Day-to-day project work is reviewed in Builder → Source control."
        />
    );
}
