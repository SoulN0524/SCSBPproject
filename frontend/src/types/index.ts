export interface Asset {
    name: string;
    current: number;
    total: number;
    alert?: boolean;
}

export interface Consumable {
    name: string;
    current: number;
    total: number;
}

export interface Notice {
    name: string;
    rate: string;
    days: string;
}

export interface ChartData {
    labels: string[];
    idle: number[];
    reserved: number[];
    borrowed: number[];
    overdue: number[];
}

export interface AppState {
    assets: Asset[];
    consumables: Consumable[];
    notices: Notice[];
    chartData: ChartData;
}
